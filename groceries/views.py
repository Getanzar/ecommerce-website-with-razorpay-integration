from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseBadRequest
from django.conf import settings
from django.views.decorators.http import require_POST

from .cart import GroceryCart
from .forms import GroceryCheckoutForm, GroceryProductForm, GroceryStoreForm
from .models import GroceryCategory, GroceryOrder, GroceryOrderItem, GroceryProduct, GroceryServiceArea, GroceryStore


def _kirana_seller(request):
    seller = getattr(request.user, "seller_profile", None)
    category = seller.business_category.lower() if seller else ""
    if not seller or not seller.is_approved or not any(word in category for word in ("grocery", "kirana", "supermarket")):
        raise PermissionDenied
    return seller


def grocery_home(request):
    pincode = request.GET.get("pincode", request.session.get("grocery_pincode", "")).strip()
    area = GroceryServiceArea.objects.filter(pincode=pincode, is_active=True).first()
    stores = GroceryStore.objects.none()
    if area:
        request.session["grocery_pincode"] = pincode
        stores = area.stores.filter(pincode=pincode, accepts_orders=True, seller__status="approved")
    return render(request, "groceries/home.html", {"stores": stores, "pincode": pincode, "area": area})


def store_detail(request, slug):
    store = get_object_or_404(GroceryStore, slug=slug, accepts_orders=True, seller__status="approved")
    pincode = request.GET.get("pincode", request.session.get("grocery_pincode", "")).strip()
    if store.pincode != pincode or not store.service_areas.filter(pincode=pincode, is_active=True).exists():
        messages.error(request, "This store does not deliver to that pincode.")
        return redirect("grocery_home")
    products = store.products.filter(is_active=True, stock__gt=0).select_related("category", "store__seller")
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(brand__icontains=query))
    if category:
        products = products.filter(category__slug=category)
    categories = GroceryCategory.objects.filter(products__store=store, products__is_active=True).distinct()
    return render(request, "groceries/store.html", {"store": store, "products": products, "categories": categories, "pincode": pincode, "selected_category": category})


def cart_detail(request):
    cart = GroceryCart(request)
    rows = cart.items()
    store = rows[0]["product"].store if rows else None
    from payments.pricing import build_grocery_pricing
    pricing = build_grocery_pricing(rows, store) if store else None
    return render(request, "groceries/cart.html", {"rows": rows, "store": store, "subtotal": cart.subtotal, "total": pricing["grand_total"] if pricing else 0, "pricing": pricing})


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(GroceryProduct.objects.select_related("store"), pk=product_id, is_active=True, stock__gt=0)
    if not product.store.accepts_orders:
        messages.error(request, "This store is currently closed.")
        return redirect("grocery_home")
    pincode = request.session.get("grocery_pincode", "")
    if product.store.pincode != pincode or not product.store.service_areas.filter(pincode=pincode, is_active=True).exists():
        messages.error(request, "Select a serviceable delivery pincode before adding products.")
        return redirect("grocery_home")
    try:
        GroceryCart(request).add(product, max(1, int(request.POST.get("quantity", 1))))
        messages.success(request, f"{product.name} added to cart.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("grocery_store", slug=product.store.slug)


@require_POST
def cart_remove(request, product_id):
    GroceryCart(request).remove(product_id)
    return redirect("grocery_cart")


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(GroceryProduct, pk=product_id)
    try:
        quantity = int(request.POST.get("quantity", ""))
        if quantity < 0:
            raise ValueError
        GroceryCart(request).set_quantity(product, quantity)
        if quantity > product.stock:
            messages.info(request, f"Quantity adjusted to the {product.stock} currently in stock.")
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid grocery quantity between 0 and 20.")
    return redirect("grocery_cart")


@login_required
@transaction.atomic
def checkout(request):
    cart = GroceryCart(request)
    rows = cart.items()
    if not rows:
        return redirect("grocery_home")
    store = rows[0]["product"].store
    from payments.pricing import build_grocery_pricing
    pricing = build_grocery_pricing(rows, store)
    if not store.accepts_orders:
        messages.error(request, "This store is currently closed.")
        return redirect("grocery_cart")
    form = GroceryCheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        area = store.service_areas.filter(pincode=form.cleaned_data["pincode"], is_active=True).first()
        if not area or store.pincode != form.cleaned_data["pincode"]:
            form.add_error("pincode", "This store does not deliver to that pincode. Local grocery delivery requires the store and customer to have the same pincode.")
        elif area.delivery_mode != "local":
            messages.error(request, "Groceries are available only through local delivery in the store pincode.")
        elif cart.subtotal < store.minimum_order:
            messages.error(request, f"Minimum order is ₹{store.minimum_order}.")
        else:
            locked = {p.pk: p for p in GroceryProduct.objects.select_for_update().filter(pk__in=[r["product"].pk for r in rows])}
            if any(locked[r["product"].pk].stock < r["quantity"] for r in rows):
                messages.error(request, "Some products no longer have enough stock. Review your cart.")
                return redirect("grocery_cart")
            order = form.save(commit=False)
            order.user, order.store = request.user, store
            order.subtotal = pricing["merchant_subtotal"] + pricing["platform_fee"]
            order.delivery_fee = store.delivery_fee
            order.total, order.delivery_mode = pricing["grand_total"], "local"
            if order.payment_method == "online":
                from payments.services import create_razorpay_order
                provider_order = create_razorpay_order(
                    order.total, f"grocery-{request.user.pk}-{timezone.now().timestamp():.0f}",
                    {"channel": "grocery", "user_id": str(request.user.pk)},
                )
                order.razorpay_order_id = provider_order["id"]
            order.save()
            for row in rows:
                product = locked[row["product"].pk]
                GroceryOrderItem.objects.create(order=order, product=product, product_name=product.name, unit=product.unit, unit_price=product.customer_price, quantity=row["quantity"])
                product.stock -= row["quantity"]
                product.save(update_fields=["stock"])
            from payments.services import create_breakdown, create_local_seller_delivery_charge, create_payment_transaction
            create_breakdown(order, pricing)
            create_local_seller_delivery_charge(order, store.seller, store.pincode, order.pincode, store.delivery_fee)
            create_payment_transaction(order, order.razorpay_order_id)
            cart.clear()
            from .emails import send_grocery_order_email
            send_grocery_order_email(order)
            if order.payment_method == "online":
                return render(request, "groceries/payment.html", {"order": order, "razorpay_key_id": settings.RAZORPAY_KEY_ID})
            return redirect("grocery_order_success", order_id=order.pk)
    return render(request, "groceries/checkout.html", {"form": form, "rows": rows, "store": store, "subtotal": cart.subtotal, "total": pricing["grand_total"], "pricing": pricing})


@login_required
@require_POST
def payment_confirm(request, order_id):
    order = get_object_or_404(GroceryOrder, pk=order_id, user=request.user, payment_method="online")
    params = {key: request.POST.get(key, "") for key in ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature")}
    if params["razorpay_order_id"] != order.razorpay_order_id:
        return HttpResponseBadRequest("Invalid payment order")
    try:
        from payments.services import capture_browser_payment
        capture_browser_payment(order, params["razorpay_order_id"], params["razorpay_payment_id"], params["razorpay_signature"])
    except Exception:
        return HttpResponseBadRequest("Payment verification failed")
    order.payment_status = "Paid"
    order.razorpay_payment_id = params["razorpay_payment_id"]
    order.save(update_fields=["payment_status", "razorpay_payment_id", "updated_at"])
    from .settlements import create_grocery_settlement
    create_grocery_settlement(order)
    return redirect("grocery_order_success", order_id=order.pk)


@login_required
def payment_retry(request, order_id):
    order = get_object_or_404(GroceryOrder, pk=order_id, user=request.user, payment_method="online")
    if order.payment_status == "Paid":
        return redirect("grocery_order_success", order_id=order.pk)
    if order.payment_status != "Pending" or order.status == "cancelled":
        messages.error(request, "This grocery order is not available for payment.")
        return redirect("grocery_orders")
    return render(request, "groceries/payment.html", {"order": order, "razorpay_key_id": settings.RAZORPAY_KEY_ID})


@login_required
def order_success(request, order_id):
    order = get_object_or_404(GroceryOrder.objects.prefetch_related("items"), pk=order_id, user=request.user)
    return render(request, "groceries/order_success.html", {"order": order})


@login_required
def my_orders(request):
    return render(request, "groceries/my_orders.html", {"orders": request.user.grocery_orders.select_related("store").prefetch_related("items")})


@login_required
def seller_dashboard(request):
    seller = _kirana_seller(request)
    store = GroceryStore.objects.filter(seller=seller).first()
    return render(request, "groceries/seller/dashboard.html", {"seller": seller, "store": store, "products": store.products.all() if store else [], "orders": store.orders.all()[:10] if store else []})


@login_required
def seller_setup(request):
    seller = _kirana_seller(request)
    store = GroceryStore.objects.filter(seller=seller).first()
    form = GroceryStoreForm(request.POST or None, request.FILES or None, instance=store, initial={"name": seller.store_name, "phone": seller.business_phone, "address": seller.business_address})
    if request.method == "POST" and form.is_valid():
        store = form.save(commit=False); store.seller = seller; store.save(); form.save_m2m()
        messages.success(request, "Kirana store details saved.")
        return redirect("grocery_seller_dashboard")
    return render(request, "groceries/seller/form.html", {"seller": seller, "form": form, "title": "Store setup"})


@login_required
@require_POST
def seller_toggle_store(request):
    store = get_object_or_404(GroceryStore, seller=_kirana_seller(request))
    store.accepts_orders = not store.accepts_orders; store.save(update_fields=["accepts_orders"])
    messages.success(request, f"Store is now {'open' if store.accepts_orders else 'closed'}.")
    return redirect("grocery_seller_dashboard")


@login_required
def seller_product(request, product_id=None):
    seller = _kirana_seller(request); store = get_object_or_404(GroceryStore, seller=seller)
    product = get_object_or_404(GroceryProduct, pk=product_id, store=store) if product_id else None
    form = GroceryProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False); product.store = store; product.save()
        messages.success(request, "Grocery product saved.")
        return redirect("grocery_seller_dashboard")
    return render(request, "groceries/seller/form.html", {"seller": seller, "form": form, "title": "Edit product" if product else "Add product"})


@login_required
def seller_orders(request):
    store = get_object_or_404(GroceryStore, seller=_kirana_seller(request))
    return render(request, "groceries/seller/orders.html", {"seller": store.seller, "store": store, "orders": store.orders.prefetch_related("items")})


@login_required
@require_POST
def seller_update_order(request, order_id):
    store = get_object_or_404(GroceryStore, seller=_kirana_seller(request)); order = get_object_or_404(GroceryOrder, pk=order_id, store=store)
    if order.payment_method == "online" and order.payment_status != "Paid":
        messages.error(request, "This online order cannot be prepared until payment is confirmed.")
        return redirect("grocery_seller_orders")
    transitions = {"placed": {"accepted", "cancelled"}, "accepted": {"packing", "cancelled"}, "packing": {"ready", "cancelled"}, "ready": set(), "shipped": set()}
    status = request.POST.get("status", "")
    if status not in transitions.get(order.status, set()):
        messages.error(request, "That status change is not allowed.")
    else:
        if status == "cancelled":
            for item in order.items.select_related("product"):
                item.product.stock += item.quantity
                item.product.save(update_fields=["stock"])
        order.status = status
        if status == "ready":
            from delivery.services import ensure_grocery_delivery
            ensure_grocery_delivery(order)
        order.save()
        if status == "cancelled" and order.payment_method == "online" and order.payment_status == "Paid":
            try:
                from payments.services import request_refund
                request_refund(order, order.total, f"Grocery order #{order.pk} cancelled by store")
            except Exception as exc:
                messages.error(request, f"Order cancelled, but refund needs review: {exc}")
        from .emails import send_grocery_order_email
        send_grocery_order_email(order, status_update=True)
        messages.success(request, f"Order #{order.pk} updated.")
    return redirect("grocery_seller_orders")
