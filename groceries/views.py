from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseBadRequest
from django.conf import settings
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from .cart import GroceryCart
from .forms import GroceryCheckoutForm, GroceryProductForm, GroceryStoreForm, GroceryOptionFormSet
from .models import GroceryCategory, GroceryOrder, GroceryOrderItem, GroceryProduct, GroceryProductOption, GroceryServiceArea, GroceryStore
from .options import available_products, with_pack_options, prepare_product, resolve_option, GroceryInventoryError, lock_grocery_rows, reserve_order_items, restore_order_stock


def _kirana_seller(request):
    seller = getattr(request.user, "seller_profile", None)
    if not seller or not seller.is_approved or seller.business_segment != "grocery":
        raise PermissionDenied
    return seller


def grocery_home(request):
    pincode = request.GET.get("pincode", request.session.get("grocery_pincode", "")).strip()
    area = GroceryServiceArea.objects.filter(pincode=pincode, is_active=True).first()
    if area:
        request.session["grocery_pincode"] = pincode
    available = _available_grocery_products(pincode)
    categories = GroceryCategory.objects.filter(products__in=available).annotate(
        available_count=Count("products", distinct=True),
    ).prefetch_related(Prefetch(
        "products", queryset=available.exclude(image="").order_by("pk")[:4],
        to_attr="collage_products",
    )) if area else GroceryCategory.objects.none()
    return render(request, "groceries/home.html", {"grocery_categories": categories, "pincode": pincode, "area": area})


def _available_grocery_products(pincode):
    return available_products().filter(
        store__pincode=pincode,
        store__accepts_orders=True, store__seller__status="approved",
        store__service_areas__pincode=pincode, store__service_areas__is_active=True,
    ).select_related("store__seller", "category")


def category_detail(request, slug):
    category = get_object_or_404(GroceryCategory, slug=slug)
    pincode = request.GET.get("pincode", request.session.get("grocery_pincode", "")).strip()
    area = GroceryServiceArea.objects.filter(pincode=pincode, is_active=True).first()
    if not area:
        messages.info(request, "Choose an available delivery pincode to browse groceries.")
        return redirect("grocery_home")
    request.session["grocery_pincode"] = pincode
    products = with_pack_options(_available_grocery_products(pincode).filter(category=category))
    query = request.GET.get("q", "").strip()[:100]
    if query:
        products = products.filter(Q(name__icontains=query) | Q(brand__icontains=query))
    page = Paginator(products.order_by("name", "pk"), 24).get_page(request.GET.get("page"))
    for product in page:
        prepare_product(product)
    cart = GroceryCart(request)
    return render(request, "groceries/category.html", {
        "category": category, "page": page, "pincode": pincode, "query": query,
        "cart_store_id": cart.data.get("store_id"),
    })


def store_detail(request, slug):
    store = get_object_or_404(GroceryStore, slug=slug, accepts_orders=True, seller__status="approved")
    pincode = request.GET.get("pincode", request.session.get("grocery_pincode", "")).strip()
    if store.pincode != pincode or not store.service_areas.filter(pincode=pincode, is_active=True).exists():
        messages.error(request, "This store does not deliver to that pincode.")
        return redirect("grocery_home")
    products = with_pack_options(available_products(store.products.all()).select_related("category", "store__seller"))
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(brand__icontains=query))
    if category:
        products = products.filter(category__slug=category)
    products = list(products)
    for product in products:
        prepare_product(product)
    categories = GroceryCategory.objects.filter(products__store=store, products__is_active=True).distinct()
    return render(request, "groceries/store.html", {"store": store, "products": products, "grocery_categories": categories, "pincode": pincode, "selected_category": category})


def cart_detail(request):
    cart = GroceryCart(request)
    rows = cart.items()
    store = rows[0]["product"].store if rows else None
    from payments.pricing import build_grocery_pricing
    pricing = build_grocery_pricing(rows, store) if store else None
    return render(request, "groceries/cart.html", {"rows": rows, "store": store, "subtotal": cart.subtotal, "total": pricing["grand_total"] if pricing else 0, "pricing": pricing})


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(GroceryProduct.objects.select_related("store", "category"), pk=product_id, is_active=True, store__seller__status="approved")
    if not product.store.accepts_orders:
        messages.error(request, "This store is currently closed.")
        return redirect("grocery_home")
    pincode = request.session.get("grocery_pincode", "")
    if product.store.pincode != pincode or not product.store.service_areas.filter(pincode=pincode, is_active=True).exists():
        messages.error(request, "Select a serviceable delivery pincode before adding products.")
        return redirect("grocery_home")
    try:
        option = resolve_option(product, request.POST.get("option_id"))
        GroceryCart(request).add(product, int(request.POST.get("quantity", 1)), option=option)
        messages.success(request, f"{product.name} ({option.unit}) added to cart.")
    except ValueError as exc:
        messages.error(request, str(exc))
    if request.POST.get("category_slug") == product.category.slug:
        return redirect(reverse("grocery_category", args=[product.category.slug]) + "?" + urlencode({"pincode": pincode}))
    return redirect("grocery_store", slug=product.store.slug)


@require_POST
def cart_remove(request, product_id):
    try:
        option_id = int(request.POST["option_id"]) if request.POST.get("option_id") else None
        GroceryCart(request).remove(product_id, option_id)
    except (TypeError, ValueError):
        messages.error(request, "Choose a valid pack size.")
    return redirect("grocery_cart")


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(GroceryProduct, pk=product_id)
    try:
        quantity = int(request.POST.get("quantity", ""))
        if quantity < 0:
            raise ValueError
        option = product.options.get(pk=int(request.POST["option_id"])) if request.POST.get("option_id") else product.default_option
        GroceryCart(request).set_quantity(product, quantity, option=option)
        if quantity > option.stock:
            messages.info(request, f"Quantity adjusted to the {option.stock} currently in stock.")
    except (TypeError, ValueError, GroceryProductOption.DoesNotExist):
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
            try:
                rows = lock_grocery_rows(rows)
            except GroceryInventoryError as exc:
                messages.error(request, str(exc))
                return redirect("grocery_cart")
            pricing = build_grocery_pricing(rows, store)
            order = form.save(commit=False)
            order.user, order.store = request.user, store
            order.subtotal = pricing["merchant_subtotal"] + pricing["platform_fee"]
            order.delivery_fee = pricing["delivery_fee"]
            order.total, order.delivery_mode = pricing["grand_total"], "local"
            if order.payment_method == "online":
                from payments.services import create_razorpay_order
                provider_order = create_razorpay_order(
                    order.total, f"grocery-{request.user.pk}-{timezone.now().timestamp():.0f}",
                    {"channel": "grocery", "user_id": str(request.user.pk)},
                )
                order.razorpay_order_id = provider_order["id"]
            order.save()
            reserve_order_items(order, rows)
            from payments.services import create_breakdown, create_local_seller_delivery_charge, create_payment_transaction
            create_breakdown(order, pricing)
            create_local_seller_delivery_charge(order, store.seller, store.pincode, order.pincode, order.delivery_fee)
            create_payment_transaction(order, order.razorpay_order_id)
            cart.clear()
            from mobile_api.notifications import notify_sellers_of_order
            notify_sellers_of_order(order)
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
@never_cache
def my_orders(request):
    return render(request, "groceries/my_orders.html", {"orders": request.user.grocery_orders.select_related("store").prefetch_related("items")})


@login_required
def seller_dashboard(request):
    seller = _kirana_seller(request)
    store = GroceryStore.objects.filter(seller=seller).first()
    return render(request, "groceries/seller/dashboard.html", {"seller": seller, "store": store, "products": with_pack_options(store.products.all()) if store else [], "orders": store.orders.all()[:10] if store else []})


@login_required
@transaction.atomic
def seller_setup(request):
    seller = _kirana_seller(request)
    store = GroceryStore.objects.filter(seller=seller).first()
    form = GroceryStoreForm(request.POST or None, request.FILES or None, instance=store, initial={"name": seller.store_name, "phone": seller.business_phone, "address": seller.business_address} if store is None else None)
    if request.method == "POST" and form.is_valid():
        store = form.save(commit=False); store.seller = seller; store.save(); form.save_m2m()
        from accounts.seller_profile import sync_store_location
        sync_store_location(store)
        messages.success(request, "Kirana store details saved.")
        return redirect("grocery_seller_dashboard")
    return render(request, "dashboard/seller/settings.html", {"seller": seller, "form": form, "title": "Grocery store settings", "store": store})


@login_required
@require_POST
def seller_toggle_store(request):
    store = get_object_or_404(GroceryStore, seller=_kirana_seller(request))
    store.accepts_orders = not store.accepts_orders; store.save(update_fields=["accepts_orders"])
    messages.success(request, f"Store is now {'open' if store.accepts_orders else 'closed'}.")
    return redirect("grocery_seller_dashboard")


@login_required
@transaction.atomic
def seller_product(request, product_id=None):
    seller = _kirana_seller(request); store = get_object_or_404(GroceryStore, seller=seller)
    if product_id is None and (store.latitude is None or store.longitude is None):
        messages.error(request, "Set and verify your store location in Store settings before adding products. This saved location is used as the pickup point for every grocery delivery.")
        return redirect("grocery_seller_setup")
    product = get_object_or_404(GroceryProduct.objects.select_for_update(), pk=product_id, store=store) if product_id else GroceryProduct(store=store)
    form = GroceryProductForm(request.POST or None, request.FILES or None, instance=product)
    sizes_submitted = "sizes-TOTAL_FORMS" in request.POST
    sizes = GroceryOptionFormSet(request.POST if sizes_submitted else None, instance=product, prefix="sizes", queryset=product.options.filter(is_default=False, is_active=True) if product.pk else GroceryProductOption.objects.none())
    valid = form.is_valid() if request.method == "POST" else False
    sizes_valid = sizes.is_valid() if sizes_submitted else True
    if request.method == "POST" and valid and sizes_valid:
        product = form.save(commit=False); product.store = store; product.save()
        if sizes_submitted:
            sizes.instance = product
            sizes.save()
        messages.success(request, "Grocery product and pack sizes saved.")
        return redirect("grocery_seller_dashboard")
    return render(request, "groceries/seller/product_form.html", {"seller": seller, "form": form, "sizes": sizes, "title": "Edit product" if product.pk else "Add product"})


@login_required
def seller_orders(request):
    store = get_object_or_404(GroceryStore, seller=_kirana_seller(request))
    return render(request, "groceries/seller/orders.html", {"seller": store.seller, "store": store, "orders": store.orders.prefetch_related("items")})


@login_required
@require_POST
@transaction.atomic
def seller_update_order(request, order_id):
    store = get_object_or_404(GroceryStore, seller=_kirana_seller(request)); order = get_object_or_404(GroceryOrder.objects.select_for_update(), pk=order_id, store=store)
    if order.payment_method == "online" and order.payment_status != "Paid":
        messages.error(request, "This online order cannot be prepared until payment is confirmed.")
        return redirect("grocery_seller_orders")
    transitions = {"placed": {"accepted", "cancelled"}, "accepted": {"packing", "cancelled"}, "packing": {"ready", "cancelled"}, "ready": set(), "shipped": set()}
    status = request.POST.get("status", "")
    if status not in transitions.get(order.status, set()):
        messages.error(request, "That status change is not allowed.")
    else:
        if status == "cancelled":
            restore_order_stock(order)
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
