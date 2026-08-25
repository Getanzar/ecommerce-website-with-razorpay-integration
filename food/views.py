from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from django.http import Http404
from django.http import HttpResponseBadRequest
from django.conf import settings
import razorpay
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .cart import FoodCart
from .forms import FoodCheckoutForm, MenuItemForm, MenuOptionFormSet, MenuSectionForm, RestaurantForm
from .models import FoodOrder, FoodOrderItem, FoodServiceArea, MenuItem, MenuItemOption, Restaurant


def _restaurant_seller(request):
    seller = getattr(request.user, "seller_profile", None)
    if not seller or not seller.is_approved:
        raise Http404
    category = seller.business_category.lower()
    if "food" not in category and "restaurant" not in category:
        raise Http404
    return seller


def restaurant_list(request):
    pincode = request.GET.get("pincode", request.session.get("food_pincode", "243638")).strip()
    area = FoodServiceArea.objects.filter(pincode=pincode, is_active=True).first()
    if area:
        request.session["food_pincode"] = pincode
    restaurants = Restaurant.objects.none()
    if area:
        restaurants = area.restaurants.filter(pincode=pincode, accepts_orders=True, seller__status="approved")
    return render(request, "food/restaurant_list.html", {"restaurants": restaurants, "pincode": pincode, "serviceable": bool(area)})


def restaurant_menu(request, slug):
    restaurant = get_object_or_404(Restaurant, slug=slug, accepts_orders=True, seller__status="approved")
    pincode = request.GET.get("pincode", request.session.get("food_pincode", "243638")).strip()
    if restaurant.pincode != pincode or not restaurant.service_areas.filter(pincode=pincode, is_active=True).exists():
        messages.error(request, "This restaurant does not deliver to that pincode.")
        return redirect(f"/food/?pincode={pincode}")
    sections = restaurant.sections.prefetch_related("items__options")
    return render(request, "food/menu.html", {"restaurant": restaurant, "sections": sections, "pincode": pincode})


def cart_detail(request):
    cart = FoodCart(request)
    rows = cart.items()
    restaurant = rows[0]["option"].item.restaurant if rows else None
    from payments.pricing import build_food_pricing
    pricing = build_food_pricing(rows, restaurant) if restaurant else None
    return render(request, "food/cart.html", {"rows": rows, "restaurant": restaurant, "subtotal": cart.subtotal, "total": pricing["grand_total"] if pricing else Decimal("0"), "pricing": pricing})


@require_POST
def cart_add(request, option_id):
    option = get_object_or_404(MenuItemOption.objects.select_related("item__restaurant"), pk=option_id, is_available=True, item__is_available=True)
    restaurant = option.item.restaurant
    if not restaurant.accepts_orders:
        messages.error(request, "This restaurant is currently closed and is not accepting orders.")
        return redirect("food_home")
    pincode = request.session.get("food_pincode", "243638")
    if restaurant.pincode != pincode or not restaurant.service_areas.filter(pincode=pincode, is_active=True).exists():
        messages.error(request, "Select a serviceable delivery pincode before adding food.")
        return redirect("food_home")
    try:
        FoodCart(request).add(option, max(1, int(request.POST.get("quantity", 1))), request.POST.get("note", "").strip())
        messages.success(request, f"{option.item.name} added to your food cart.")
    except ValueError as exc:
        messages.error(request, str(exc) + " Clear the cart before switching restaurants.")
    return redirect("food_restaurant", slug=option.item.restaurant.slug)


@require_POST
def cart_remove(request, option_id):
    FoodCart(request).remove(option_id)
    return redirect("food_cart")


@require_POST
def cart_update(request, option_id):
    get_object_or_404(MenuItemOption, pk=option_id, is_available=True, item__is_available=True)
    try:
        quantity = int(request.POST.get("quantity", ""))
        if quantity < 0:
            raise ValueError
        FoodCart(request).set_quantity(option_id, quantity)
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid food quantity between 0 and 20.")
    return redirect("food_cart")


@login_required
@transaction.atomic
def checkout(request):
    cart = FoodCart(request)
    rows = cart.items()
    if not rows:
        messages.info(request, "Your food cart is empty.")
        return redirect("food_home")
    restaurant = rows[0]["option"].item.restaurant
    from payments.pricing import build_food_pricing
    pricing = build_food_pricing(rows, restaurant)
    if not restaurant.accepts_orders:
        messages.error(request, "This restaurant is currently closed. Please order when it reopens.")
        return redirect("food_cart")
    form = FoodCheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pincode = form.cleaned_data["pincode"]
        if restaurant.pincode != pincode or not restaurant.service_areas.filter(pincode=pincode, is_active=True).exists():
            form.add_error("pincode", "This restaurant does not deliver to that pincode. Local food delivery requires the restaurant and customer to have the same pincode.")
        elif cart.subtotal < restaurant.minimum_order:
            messages.error(request, f"Minimum order is ₹{restaurant.minimum_order}.")
        else:
            order = form.save(commit=False)
            order.user = request.user
            order.restaurant = restaurant
            order.subtotal = pricing["merchant_subtotal"] + pricing["platform_fee"]
            order.delivery_fee = restaurant.delivery_fee
            order.total = pricing["grand_total"]
            if order.payment_method == "online":
                from payments.services import create_razorpay_order
                provider_order = create_razorpay_order(
                    order.total, f"food-{request.user.pk}-{timezone.now().timestamp():.0f}",
                    {"channel": "food", "user_id": str(request.user.pk)},
                )
                order.razorpay_order_id = provider_order["id"]
            order.save()
            for row in rows:
                option = row["option"]
                FoodOrderItem.objects.create(order=order, menu_item=option.item, option=option, item_name=option.item.name, option_name=option.name, unit_price=option.customer_price, quantity=row["quantity"], customer_note=row["note"])
            from payments.services import create_breakdown, create_local_seller_delivery_charge, create_payment_transaction
            create_breakdown(order, pricing)
            create_local_seller_delivery_charge(
                order, restaurant.seller, restaurant.pincode, order.pincode, restaurant.delivery_fee,
            )
            create_payment_transaction(order, order.razorpay_order_id)
            cart.clear()
            if order.payment_method == "online":
                return render(request, "food/payment.html", {"order": order, "razorpay_key_id": settings.RAZORPAY_KEY_ID})
            return redirect("food_order_success", order_id=order.pk)
    return render(request, "food/checkout.html", {"form": form, "rows": rows, "restaurant": restaurant, "subtotal": cart.subtotal, "total": pricing["grand_total"], "pricing": pricing})


@login_required
def order_success(request, order_id):
    order = get_object_or_404(FoodOrder.objects.prefetch_related("items"), pk=order_id, user=request.user)
    return render(request, "food/order_success.html", {"order": order})


@login_required
def payment_confirm(request, order_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    order = get_object_or_404(FoodOrder, pk=order_id, user=request.user, payment_method="online")
    params = {key: request.POST.get(key, "") for key in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature")}
    if params["razorpay_order_id"] != order.razorpay_order_id:
        return HttpResponseBadRequest("Invalid payment order")
    try:
        from payments.services import capture_browser_payment
        capture_browser_payment(
            order, params["razorpay_order_id"], params["razorpay_payment_id"], params["razorpay_signature"],
        )
    except (razorpay.errors.SignatureVerificationError, ValueError):
        return HttpResponseBadRequest("Payment verification failed")
    order.payment_status = "Paid"
    order.razorpay_payment_id = params["razorpay_payment_id"]
    order.save(update_fields=["payment_status", "razorpay_payment_id", "updated_at"])
    from .settlements import create_food_settlement
    create_food_settlement(order)
    return redirect("food_order_success", order_id=order.pk)


@login_required
def payment_retry(request, order_id):
    order = get_object_or_404(FoodOrder, pk=order_id, user=request.user, payment_method="online")
    if order.payment_status == "Paid":
        return redirect("food_order_success", order_id=order.pk)
    if order.payment_status != "Pending" or order.status == "cancelled":
        messages.error(request, "This food order is not available for payment.")
        return redirect("food_orders")
    return render(request, "food/payment.html", {"order": order, "razorpay_key_id": settings.RAZORPAY_KEY_ID})


@login_required
def my_orders(request):
    return render(request, "food/my_orders.html", {"orders": request.user.food_orders.select_related("restaurant").prefetch_related("items")})


@login_required
def seller_menu(request):
    seller = _restaurant_seller(request)
    restaurant = Restaurant.objects.filter(seller=seller).first()
    return render(request, "food/seller/menu.html", {"seller": seller, "restaurant": restaurant})


@login_required
def seller_restaurant_setup(request):
    seller = _restaurant_seller(request)
    restaurant = Restaurant.objects.filter(seller=seller).first()
    form = RestaurantForm(request.POST or None, request.FILES or None, instance=restaurant, initial={"name": seller.store_name})
    if request.method == "POST" and form.is_valid():
        restaurant = form.save(commit=False)
        restaurant.seller = seller
        restaurant.save()
        form.save_m2m()
        messages.success(request, "Restaurant details saved.")
        return redirect("food_seller_menu")
    return render(request, "food/seller/restaurant_form.html", {"form": form})


@login_required
@require_POST
def seller_toggle_restaurant(request):
    seller = _restaurant_seller(request)
    restaurant = get_object_or_404(Restaurant, seller=seller)
    restaurant.accepts_orders = not restaurant.accepts_orders
    restaurant.save(update_fields=["accepts_orders"])
    state = "open and accepting orders" if restaurant.accepts_orders else "closed"
    messages.success(request, f"{restaurant.name} is now {state}.")
    return redirect("food_seller_menu")


@login_required
@transaction.atomic
def seller_add_menu_item(request):
    seller = _restaurant_seller(request)
    restaurant = get_object_or_404(Restaurant, seller=seller)
    item = MenuItem(restaurant=restaurant)
    form = MenuItemForm(request.POST or None, request.FILES or None, instance=item, restaurant=restaurant)
    formset = MenuOptionFormSet(request.POST or None, instance=item)
    for option_form in formset.forms:
        option_form.fields["price"].label = "Your selling price"
        option_form.fields["price"].help_text = "The platform fee is added for the customer."
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        item = form.save(commit=False)
        item.restaurant = restaurant
        item.save()
        formset.instance = item
        options = formset.save()
        if not options:
            transaction.set_rollback(True)
            form.add_error(None, "Add at least one size and price.")
        else:
            messages.success(request, "Menu item added.")
            return redirect("food_seller_menu")
    return render(request, "food/seller/menu_item_form.html", {"form": form, "formset": formset})


@login_required
@transaction.atomic
def seller_edit_menu_item(request, item_id):
    seller = _restaurant_seller(request)
    item = get_object_or_404(MenuItem, pk=item_id, restaurant__seller=seller)
    form = MenuItemForm(request.POST or None, request.FILES or None, instance=item, restaurant=item.restaurant)
    formset = MenuOptionFormSet(request.POST or None, instance=item)
    for option_form in formset.forms:
        option_form.fields["price"].label = "Your selling price"
        option_form.fields["price"].help_text = "The platform fee is added for the customer."
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save(); formset.save()
        messages.success(request, "Menu item updated.")
        return redirect("food_seller_menu")
    return render(request, "food/seller/menu_item_form.html", {"form": form, "formset": formset, "editing": True})


@login_required
def seller_add_section(request):
    seller = _restaurant_seller(request)
    restaurant = get_object_or_404(Restaurant, seller=seller)
    form = MenuSectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        section = form.save(commit=False)
        section.restaurant = restaurant
        section.save()
        return redirect("food_seller_add_item")
    return render(request, "food/seller/section_form.html", {"form": form})


@login_required
def seller_orders(request):
    seller = _restaurant_seller(request)
    restaurant = get_object_or_404(Restaurant, seller=seller)
    return render(request, "food/seller/orders.html", {"orders": restaurant.orders.prefetch_related("items")})


@login_required
def seller_update_order(request, order_id):
    seller = _restaurant_seller(request)
    order = get_object_or_404(FoodOrder, pk=order_id, restaurant__seller=seller)
    if request.method == "POST":
        if order.payment_method == "online" and order.payment_status != "Paid":
            messages.error(request, "This online order cannot be prepared until payment is confirmed.")
            return redirect("food_seller_orders")
        status = request.POST.get("status", "")
        transitions = {"placed": {"accepted", "cancelled"}, "accepted": {"preparing", "cancelled"}, "preparing": {"ready"}, "ready": set(), "out_for_delivery": set(), "delivered": set(), "cancelled": set()}
        if status in transitions.get(order.status, set()):
            order.status = status
            order.save(update_fields=["status", "payment_status", "updated_at"])
            if status == "ready":
                from delivery.services import ensure_food_delivery
                ensure_food_delivery(order)
            if status == "cancelled" and order.payment_method == "online" and order.payment_status == "Paid":
                try:
                    from payments.services import request_refund
                    request_refund(order, order.total, f"Food order #{order.pk} cancelled by restaurant")
                except Exception as exc:
                    messages.error(request, f"Order cancelled, but refund needs review: {exc}")
            messages.success(request, f"Order #{order.id} updated.")
        else:
            messages.error(request, "That order status change is not allowed.")
    return redirect("food_seller_orders")


@login_required
def seller_toggle_item(request, item_id):
    seller = _restaurant_seller(request)
    item = get_object_or_404(MenuItem, pk=item_id, restaurant__seller=seller)
    if request.method == "POST":
        item.is_available = not item.is_available
        item.save(update_fields=["is_available"])
    return redirect("food_seller_menu")
