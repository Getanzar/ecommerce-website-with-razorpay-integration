from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
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
        stores = area.stores.filter(accepts_orders=True, seller__status="approved")
    return render(request, "groceries/home.html", {"stores": stores, "pincode": pincode, "area": area})


def store_detail(request, slug):
    store = get_object_or_404(GroceryStore, slug=slug, accepts_orders=True, seller__status="approved")
    pincode = request.GET.get("pincode", request.session.get("grocery_pincode", "")).strip()
    if not store.service_areas.filter(pincode=pincode, is_active=True).exists():
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
    total = cart.subtotal + (store.delivery_fee if store else 0)
    return render(request, "groceries/cart.html", {"rows": rows, "store": store, "subtotal": cart.subtotal, "total": total})


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(GroceryProduct.objects.select_related("store"), pk=product_id, is_active=True, stock__gt=0)
    if not product.store.accepts_orders:
        messages.error(request, "This store is currently closed.")
        return redirect("grocery_home")
    pincode = request.session.get("grocery_pincode", "")
    if not product.store.service_areas.filter(pincode=pincode, is_active=True).exists():
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


@login_required
@transaction.atomic
def checkout(request):
    cart = GroceryCart(request)
    rows = cart.items()
    if not rows:
        return redirect("grocery_home")
    store = rows[0]["product"].store
    if not store.accepts_orders:
        messages.error(request, "This store is currently closed.")
        return redirect("grocery_cart")
    form = GroceryCheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        area = store.service_areas.filter(pincode=form.cleaned_data["pincode"], is_active=True).first()
        if not area:
            form.add_error("pincode", "This store does not deliver to this pincode.")
        elif area.delivery_mode == "delhivery" and any(row["product"].is_perishable for row in rows):
            messages.error(request, "Perishable products cannot be shipped by parcel. Choose a local-delivery pincode or remove those products.")
        elif cart.subtotal < store.minimum_order:
            messages.error(request, f"Minimum order is ₹{store.minimum_order}.")
        else:
            locked = {p.pk: p for p in GroceryProduct.objects.select_for_update().filter(pk__in=[r["product"].pk for r in rows])}
            if any(locked[r["product"].pk].stock < r["quantity"] for r in rows):
                messages.error(request, "Some products no longer have enough stock. Review your cart.")
                return redirect("grocery_cart")
            order = form.save(commit=False)
            order.user, order.store = request.user, store
            order.subtotal, order.delivery_fee = cart.subtotal, store.delivery_fee
            order.total, order.delivery_mode = order.subtotal + order.delivery_fee, area.delivery_mode
            order.save()
            for row in rows:
                product = locked[row["product"].pk]
                GroceryOrderItem.objects.create(order=order, product=product, product_name=product.name, unit=product.unit, unit_price=product.customer_price, quantity=row["quantity"])
                product.stock -= row["quantity"]
                product.save(update_fields=["stock"])
            cart.clear()
            from .emails import send_grocery_order_email
            send_grocery_order_email(order)
            return redirect("grocery_order_success", order_id=order.pk)
    return render(request, "groceries/checkout.html", {"form": form, "rows": rows, "store": store, "subtotal": cart.subtotal, "total": cart.subtotal + store.delivery_fee})


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
    transitions = {"placed": {"accepted", "cancelled"}, "accepted": {"packing", "cancelled"}, "packing": {"ready", "cancelled"}, "ready": {"shipped"}, "shipped": {"delivered"}}
    status = request.POST.get("status", "")
    if status not in transitions.get(order.status, set()):
        messages.error(request, "That status change is not allowed.")
    else:
        if status == "cancelled":
            for item in order.items.select_related("product"):
                item.product.stock += item.quantity
                item.product.save(update_fields=["stock"])
        order.status = status
        if status == "shipped" and order.delivery_mode == "delhivery":
            order.courier = request.POST.get("courier", "Delhivery").strip(); order.tracking_number = request.POST.get("tracking_number", "").strip()
            if not order.tracking_number:
                messages.error(request, "Tracking number is required for Delhivery orders."); return redirect("grocery_seller_orders")
        if status == "delivered" and order.payment_method == "cod": order.payment_status = "Paid"
        order.save()
        from .emails import send_grocery_order_email
        send_grocery_order_email(order, status_update=True)
        messages.success(request, f"Order #{order.pk} updated.")
    return redirect("grocery_seller_orders")
