import json
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.utils.text import slugify
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from orders.models import (
    Order, 
    OrderItem,
    ReturnRequest,
    SupportTicket,
    SupportReply,
    OrderTimeline,
    SellerSettlement,
    )
from products.models import (
    Product,
    Category,
    ProductImage,
    SubCategory,
    ProductColor,
    ProductVariant,
    CatalogRequest,
)
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from products.models import ProductReview
from orders.models import ReturnRequest, SupportTicket
from django.db.models import Q
from django.template.loader import render_to_string
from django.contrib import messages
from django.http import HttpResponse
from django.db import IntegrityError, transaction
from django.forms import modelformset_factory
from products.models import ProductVariant
from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Count
from django.db.models.functions import TruncMonth
from django.core.exceptions import PermissionDenied
from accounts.models import SellerProfile
from .forms import ProductAudienceForm, SellerProductEditForm, SellerProductForm, SellerVariantStockForm
from .security import audit, operations_admin_required

# ✅ Only allow superusers (admins) to access dashboard
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def admin_dashboard(request):
    total_orders = Order.objects.count()
    total_revenue = (
        Order.objects.filter(status="Paid")
        .aggregate(Sum("total_price"))["total_price__sum"]
        or 0
    )
    pending_orders = Order.objects.filter(status="Pending").count()
    top_products = (
        OrderItem.objects.values("product__name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:5]
    )

    products = Product.objects.all()
    categories = Category.objects.all()
    subcategories = SubCategory.objects.all()

    context = {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "pending_orders": pending_orders,
        "top_products": top_products,
        "products": products,
        "categories": categories,
        "subcategories": subcategories,
    }
    return render(request, "dashboard/admin_dashboard.html", context)


def _approved_seller_for(request):
    """Return the active seller profile or deny dashboard access."""
    try:
        seller = request.user.seller_profile
    except SellerProfile.DoesNotExist as exc:
        raise PermissionDenied("This account is not registered as a seller.") from exc

    if not seller.is_approved:
        raise PermissionDenied("Your seller account is awaiting marketplace approval.")

    return seller


def _merchandise_seller_for(request):
    seller = _approved_seller_for(request)
    if seller.business_segment != "shop":
        raise PermissionDenied("Merchandise tools are not enabled for this selling segment.")
    return seller


@login_required
def seller_dashboard(request):
    seller = SellerProfile.objects.filter(user=request.user).first()
    if not seller or not seller.is_approved or seller.business_segment not in dict(SellerProfile.BUSINESS_SEGMENTS):
        return redirect("seller_application")
    if seller.business_segment == "grocery":
        return redirect("grocery_seller_dashboard")
    if seller.business_segment == "food":
        from food.models import Restaurant, FoodSellerSettlement
        restaurant = Restaurant.objects.filter(seller=seller).first()
        food_orders = restaurant.orders.prefetch_related("items") if restaurant else Order.objects.none()
        return render(request, "food/seller/dashboard.html", {
            "seller": seller, "restaurant": restaurant,
            "menu_count": restaurant.menu_items.count() if restaurant else 0,
            "open_order_count": food_orders.exclude(status__in=["delivered", "cancelled"]).count() if restaurant else 0,
            "recent_orders": food_orders[:8] if restaurant else [],
            "available_balance": FoodSellerSettlement.objects.filter(seller=seller, status="scheduled").aggregate(total=Sum("net_amount"))["total"] or 0,
            "paid_out": FoodSellerSettlement.objects.filter(seller=seller, status="paid").aggregate(total=Sum("net_amount"))["total"] or 0,
        })
    products = Product.objects.filter(seller=seller).order_by("-created")
    order_items = (
        OrderItem.objects.filter(product__seller=seller)
        .select_related("order", "product")
        .order_by("-order__created_at")
    )
    completed_sales = order_items.exclude(
        order__status__in=["Cancelled", "Returned"]
    ).filter(order__payment_status="Paid")
    gross_sales = completed_sales.aggregate(
        total=Sum(
            ExpressionWrapper(
                F("price") * F("quantity"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )["total"] or 0

    from products.electronics import seller_electronics_types
    context = {
        "electronics_types": seller_electronics_types(seller),
        "seller": seller,
        "order_alerts": request.user.notification_set.filter(title="New seller order", data__kind="shop")[:8],
        "product_count": products.count(),
        "live_product_count": products.filter(is_active=True).count(),
        "order_count": order_items.values("order_id").distinct().count(),
        "gross_sales": gross_sales,
        "recent_order_items": order_items[:8],
        "available_balance": SellerSettlement.objects.filter(seller=seller, status="scheduled").aggregate(total=Sum("net_amount"))["total"] or 0,
        "paid_out": SellerSettlement.objects.filter(seller=seller, status="paid").aggregate(total=Sum("net_amount"))["total"] or 0,
    }
    return render(request, "dashboard/seller/dashboard.html", context)


@login_required
def seller_products(request):
    seller = _merchandise_seller_for(request)
    products = Product.objects.filter(seller=seller).order_by("-created")
    return render(
        request,
        "dashboard/seller/products.html",
        {"seller": seller, "products": products},
    )


@login_required
@transaction.atomic
def seller_profile_settings(request):
    from accounts.seller_profile import SellerProfileForm
    seller = _approved_seller_for(request)
    seller = SellerProfile.objects.select_for_update().get(pk=seller.pk)
    form = SellerProfileForm(request.POST or None, request.FILES or None, instance=seller)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your seller profile and pickup details have been saved.")
        return redirect("seller_profile_settings")
    return render(request, "dashboard/seller/settings.html", {"seller": seller, "form": form, "title": "Seller profile", "profile_settings": True})


@login_required
def seller_edit_product(request, product_id):
    seller = _merchandise_seller_for(request)
    product = get_object_or_404(Product, id=product_id, seller=seller)
    from products.electronics import ELECTRONICS
    from .electronics import ElectronicsProductForm
    if product.category.slug == "electronics" and product.product_type in ELECTRONICS:
        form = ElectronicsProductForm(request.POST or None, request.FILES or None, instance=product, kind=product.product_type, seller=seller)
    else:
        form = SellerProductEditForm(request.POST or None, request.FILES or None, instance=product, seller=seller)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.moderation_status = Product.MODERATION_PENDING
        product.is_active = False
        product.rejection_reason = ""
        product.save()
        messages.success(request, "Changes saved and submitted for admin review.")
        return redirect("seller_products")
    return render(request, "dashboard/seller/edit_product.html", {"seller": seller, "product": product, "form": form})


@login_required
def seller_inventory(request, product_id):
    seller = _merchandise_seller_for(request)
    product = get_object_or_404(Product, id=product_id, seller=seller)
    VariantFormSet = modelformset_factory(ProductVariant, form=SellerVariantStockForm, extra=0)
    queryset = product.variants.select_related("color")
    formset = VariantFormSet(request.POST or None, queryset=queryset)
    if request.method == "POST" and formset.is_valid():
        formset.save()
        product.stock = sum(product.variants.values_list("stock", flat=True))
        product.save(update_fields=["stock"])
        messages.success(request, "Inventory updated.")
        return redirect("seller_products")
    return render(request, "dashboard/seller/inventory.html", {"seller": seller, "product": product, "formset": formset})


@require_POST
@login_required
def seller_toggle_product(request, product_id):
    seller = _merchandise_seller_for(request)
    product = get_object_or_404(Product, id=product_id, seller=seller)
    if product.moderation_status != Product.MODERATION_APPROVED:
        messages.error(request, "Only approved products can be made live.")
    else:
        product.is_active = not product.is_active
        product.save(update_fields=["is_active"])
        messages.success(request, "Listing status updated.")
    return redirect("seller_products")


@require_POST
@login_required
def seller_request_pickup(request, item_id):
    seller = _merchandise_seller_for(request)
    item = get_object_or_404(OrderItem, pk=item_id, product__seller=seller)
    from orders.pickups import queue_order_pickups
    queue_order_pickups(item.order_id, seller.pk, retry=True)
    messages.info(request, "Pickup status refreshed. Review the parcel status below; requests needing carrier review are not duplicated.")
    return redirect("seller_orders")


@login_required
def seller_orders(request):
    seller = _merchandise_seller_for(request)
    order_items = (
        OrderItem.objects.filter(product__seller=seller)
        .select_related("order", "product", "variant")
        .order_by("-order__created_at", "id")
    )
    for item in order_items:
        item.local_delivery = item.order.local_deliveries.filter(parcel_seller=seller).first()
        item.courier_charge = item.order.sellerdeliverycharges.filter(seller=seller, provider="delhivery").select_related("pickup_request").first()
    return render(
        request,
        "dashboard/seller/orders.html",
        {"seller": seller, "order_items": order_items},
    )


@require_POST
@login_required
@transaction.atomic
def seller_update_order_item(request, item_id):
    seller = _merchandise_seller_for(request)
    item = get_object_or_404(OrderItem.objects.select_related("order"), id=item_id, product__seller=seller)
    new_status = request.POST.get("status", "")
    charge = item.order.sellerdeliverycharges.filter(seller=seller, provider="delhivery").first()
    if item.order.status in {"Cancelled", "Returned", "Delivered"} or (item.order.payment_method != "cod" and item.order.payment_status != "Paid"):
        messages.error(request, "This order is closed or payment has not been confirmed.")
        return redirect("seller_orders")
    if charge and (new_status in {"shipped", "delivered"} or (new_status == "cancelled" and charge.awb_number)):
        messages.error(request, "Delhivery manages this shipment. Contact support for a booked parcel cancellation.")
        return redirect("seller_orders")
    transitions = {
        "new": {"accepted", "cancelled"}, "accepted": {"packed", "cancelled"},
        "packed": {"shipped", "cancelled"}, "shipped": {"delivered"},
        "delivered": set(), "cancelled": set(),
    }
    if new_status not in transitions.get(item.fulfillment_status, set()):
        messages.error(request, "That fulfilment status change is not allowed.")
        return redirect("seller_orders")
    if new_status == "cancelled":
        settlement = SellerSettlement.objects.filter(seller=seller, order=item.order).first()
        if settlement and settlement.status in {"paid", "processing"}:
            messages.error(request, "This item already entered payout processing. Contact marketplace support to cancel and refund it.")
            return redirect("seller_orders")
    if new_status == "shipped":
        courier = request.POST.get("courier", "").strip()
        tracking = request.POST.get("tracking_number", "").strip()
        if not courier or not tracking:
            messages.error(request, "Courier and tracking number are required for shipping.")
            return redirect("seller_orders")
        item.seller_courier, item.seller_tracking_number = courier, tracking
    item.fulfillment_status = new_status
    if new_status == "delivered":
        item.fulfilled_at = timezone.now()
    item.save()
    if new_status == "packed":
        from orders.pickups import queue_order_pickups
        queue_order_pickups(item.order_id, seller.pk)
    if new_status == "cancelled" and settlement:
        settlement.deductions_amount = min(
            settlement.net_amount, settlement.deductions_amount + item.seller_total
        )
        if settlement.payout_amount <= 0:
            settlement.status = "offset"
            settlement.processed_at = timezone.now()
        settlement.save(update_fields=["deductions_amount", "status", "processed_at", "updated_at"])
    messages.success(request, f"Order #{item.order_id} item marked {item.get_fulfillment_status_display()}.")
    return redirect("seller_orders")


@login_required
def seller_payouts(request):
    seller = _approved_seller_for(request)
    settlements = seller.settlements.select_related("order")
    totals = {
        "scheduled": settlements.filter(status="scheduled").aggregate(total=Sum("net_amount"))["total"] or 0,
        "processing": settlements.filter(status="processing").aggregate(total=Sum("net_amount"))["total"] or 0,
        "paid": settlements.filter(status="paid").aggregate(total=Sum("net_amount"))["total"] or 0,
        "on_hold": settlements.filter(status__in=["failed", "on_hold"]).aggregate(total=Sum("net_amount"))["total"] or 0,
    }
    from food.models import FoodSellerSettlement
    food_settlements = FoodSellerSettlement.objects.filter(seller=seller).select_related("order")
    return render(request, "dashboard/seller/payouts.html", {
        "seller": seller, "settlements": settlements[:100], "totals": totals,
        "food_settlements": food_settlements[:100],
        "return_balance": seller.return_debits.aggregate(total=Sum("remaining_amount"))["total"] or 0,
        "seller_notifications": seller.notifications.filter(is_read=False)[:10],
    })


@require_POST
@login_required
def seller_read_notifications(request):
    seller = _approved_seller_for(request)
    seller.notifications.filter(is_read=False).update(is_read=True)
    return redirect("seller_payouts")


@login_required
def seller_add_product(request):
    seller = _approved_seller_for(request)

    if seller.business_segment not in dict(SellerProfile.BUSINESS_SEGMENTS):
        raise PermissionDenied("Your selling segment needs review. Please contact support.")
    if seller.business_segment == "grocery":
        return redirect("grocery_seller_add_product")
    if seller.business_segment == "food":
        return redirect("food_seller_add_item")

    from products.electronics import seller_electronics_types
    electronics_types = seller_electronics_types(seller)
    if request.method == "GET" and electronics_types:
        if len(electronics_types) == 1:
            return redirect("seller_add_electronics", kind=next(iter(electronics_types)))
        return render(request, "dashboard/seller/electronics_categories.html", {"seller": seller, "electronics_types": electronics_types})

    if request.method == "POST":
        form = SellerProductForm(request.POST, request.FILES, seller=seller)
        variants_data = None
        try:
            variants_data = _parse_seller_variants(request)
        except ValueError as exc:
            form.add_error(None, str(exc))

        if form.is_valid() and variants_data is not None:
            with transaction.atomic():
                product = form.save(commit=False)
                product.seller = seller
                product.stock = sum(
                    variant["stock"]
                    for color in variants_data
                    for variant in color["variants"]
                )
                # Seller listings stay private until marketplace staff reviews them.
                product.is_active = False
                product.moderation_status = Product.MODERATION_PENDING
                product.rejection_reason = ""
                product.save()
                ProductImage.objects.create(
                    product=product,
                    image=form.cleaned_data["back_image"],
                    display_order=0,
                )

                for color_index, color_data in enumerate(variants_data):
                    color = ProductColor.objects.create(
                        product=product,
                        name=color_data["name"],
                        hex_code=color_data["hex_code"],
                        image=request.FILES.get(f"color_image_{color_index}"),
                        display_order=color_index,
                    )
                    for variant_index, variant_data in enumerate(color_data["variants"]):
                        ProductVariant.objects.create(
                            product=product,
                            color=color,
                            size=variant_data["size"],
                            stock=variant_data["stock"],
                            sku=variant_data["sku"],
                            price=variant_data["price"],
                            image=request.FILES.get(
                                f"variant_image_{color_index}_{variant_index}"
                            ),
                        )
            messages.success(
                request,
                "Product submitted. It will become visible after marketplace approval.",
            )
            return redirect("seller_products")
    else:
        form = SellerProductForm(seller=seller)

    from products.electronics import seller_electronics_types
    return render(
        request,
        "dashboard/seller/add_product.html",
        {
            "electronics_types": seller_electronics_types(seller),
            "seller": seller,
            "form": form,
        },
    )


def _parse_seller_variants(request):
    """Validate the mobile variant builder payload before creating any records."""
    try:
        colors = json.loads(request.POST.get("variants_json", ""))
    except json.JSONDecodeError as exc:
        raise ValueError("Add at least one color and size variant.") from exc
    if not isinstance(colors, list) or not colors:
        raise ValueError("Add at least one color and size variant.")
    if len(colors) > 20:
        raise ValueError("A product can have up to 20 colors.")

    parsed = []
    color_names = set()
    skus = set()
    for color in colors:
        if not isinstance(color, dict):
            raise ValueError("The color and size information is invalid.")
        name = str(color.get("name", "")).strip()
        hex_code = str(color.get("hex_code", "#000000")).strip().upper()
        if not name:
            raise ValueError("Every color needs a name.")
        if name.casefold() in color_names:
            raise ValueError(f'Color "{name}" was added more than once.')
        color_names.add(name.casefold())
        if len(hex_code) != 7 or not hex_code.startswith("#"):
            raise ValueError(f'Choose a valid color swatch for "{name}".')
        try:
            int(hex_code[1:], 16)
        except ValueError as exc:
            raise ValueError(f'Choose a valid color swatch for "{name}".') from exc

        variants = color.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError(f'Add at least one size for "{name}".')
        if len(variants) > 50:
            raise ValueError(f'Add no more than 50 sizes for "{name}".')
        parsed_variants = []
        sizes = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError(f'The size information under "{name}" is invalid.')
            size = str(variant.get("size", "")).strip()
            if not size:
                raise ValueError(f'Every variant under "{name}" needs a size.')
            if size.casefold() in sizes:
                raise ValueError(f'Size "{size}" is repeated under "{name}".')
            sizes.add(size.casefold())
            try:
                stock = int(variant.get("stock", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Enter valid stock for {name} / {size}.') from exc
            if stock < 0:
                raise ValueError(f'Stock cannot be negative for {name} / {size}.')
            sku = str(variant.get("sku", "")).strip() or None
            if sku and sku.casefold() in skus:
                raise ValueError(f'SKU "{sku}" is used more than once.')
            if sku:
                skus.add(sku.casefold())
                if ProductVariant.objects.filter(sku__iexact=sku).exists():
                    raise ValueError(f'SKU "{sku}" is already in use.')
            raw_price = str(variant.get("price", "")).strip()
            try:
                price = Decimal(raw_price) if raw_price else None
            except InvalidOperation as exc:
                raise ValueError(f'Enter a valid price for {name} / {size}.') from exc
            if price is not None and price <= 0:
                raise ValueError(f'Price must be greater than zero for {name} / {size}.')
            parsed_variants.append(
                {"size": size, "stock": stock, "sku": sku, "price": price}
            )
        parsed.append({"name": name, "hex_code": hex_code, "variants": parsed_variants})
    return parsed


def _catalog_key(name):
    """Normalize case, whitespace and punctuation for duplicate comparisons."""
    return slugify((name or "").strip())


def _matching_category(name):
    key = _catalog_key(name)
    if not key:
        return None
    return next(
        (
            category
            for category in Category.objects.only("id", "name", "slug")
            if category.slug == key or _catalog_key(category.name) == key
        ),
        None,
    )


def _matching_subcategory(parent_category, name):
    key = _catalog_key(name)
    if not parent_category or not key:
        return None
    return next(
        (
            subcategory
            for subcategory in SubCategory.objects.filter(
                category=parent_category
            ).only("id", "name", "category_id")
            if _catalog_key(subcategory.name) == key
        ),
        None,
    )


@login_required
def seller_catalog_requests(request):
    seller = _merchandise_seller_for(request)
    if request.method == "POST":
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
        request_type = request.POST.get("request_type", "").strip()
        name = request.POST.get("name", "").strip()
        parent_category = None

        error = ""
        if request_type not in {CatalogRequest.TYPE_CATEGORY, CatalogRequest.TYPE_SUBCATEGORY}:
            error = "Choose category or subcategory."
        elif not name or not _catalog_key(name):
            error = "Enter a category name using letters or numbers."
        elif request_type == CatalogRequest.TYPE_SUBCATEGORY:
            parent_category = Category.objects.filter(
                pk=request.POST.get("parent_category")
            ).first()
            if parent_category is None:
                error = "Choose a parent category for the subcategory."

        if error:
            if is_ajax:
                return JsonResponse({"error": error}, status=400)
            messages.error(request, error)
            return redirect("seller_catalog_requests")

        with transaction.atomic():
            if parent_category is not None:
                # Serialize additions under one parent so simultaneous sellers
                # cannot create equivalent subcategories at the same time.
                parent_category = Category.objects.select_for_update().get(
                    pk=parent_category.pk
                )
            existing = (
                _matching_category(name)
                if request_type == CatalogRequest.TYPE_CATEGORY
                else _matching_subcategory(parent_category, name)
            )
            created = existing is None
            if created:
                try:
                    with transaction.atomic():
                        if request_type == CatalogRequest.TYPE_CATEGORY:
                            existing = Category.objects.create(name=name)
                        else:
                            existing = SubCategory.objects.create(
                                category=parent_category, name=name
                            )
                except IntegrityError:
                    # A simultaneous request may have created the same category.
                    existing = (
                        _matching_category(name)
                        if request_type == CatalogRequest.TYPE_CATEGORY
                        else _matching_subcategory(parent_category, name)
                    )
                    created = False

        label = "category" if request_type == CatalogRequest.TYPE_CATEGORY else "subcategory"
        if created:
            notice = f'The {label} "{existing.name}" was added and is ready to use.'
            if not is_ajax:
                messages.success(request, notice)
        else:
            notice = f'The {label} "{existing.name}" already exists. You can use it now.'
            if not is_ajax:
                messages.info(request, notice)

        if is_ajax:
            return JsonResponse(
                {
                    "id": existing.pk,
                    "name": existing.name,
                    "type": request_type,
                    "parent_category": parent_category.pk if parent_category else None,
                    "created": created,
                    "message": notice,
                }
            )
        return redirect("seller_add_product")

    return render(
        request,
        "dashboard/seller/catalog_requests.html",
        {
            "seller": seller,
            "categories": Category.objects.order_by("name"),
            "catalog_requests": CatalogRequest.objects.filter(seller=seller),
        },
    )


@operations_admin_required
def sellers_management(request):
    sellers = SellerProfile.objects.select_related("user").prefetch_related(
        "products"
    )
    status = request.GET.get("status")

    if status in {"pending", "approved", "suspended"}:
        sellers = sellers.filter(status=status)
    registration_type = request.GET.get("registration_type", "")
    if registration_type in {"small", "registered"}:
        sellers = sellers.filter(registration_type=registration_type)

    context = {
        "sellers": sellers,
        "selected_status": status,
        "selected_registration_type": registration_type,
        "pending_count": SellerProfile.objects.filter(status="pending").count(),
        "approved_count": SellerProfile.objects.filter(status="approved").count(),
        "suspended_count": SellerProfile.objects.filter(status="suspended").count(),
    }
    return render(request, "dashboard/sellers_management.html", context)


@require_POST
@operations_admin_required
def update_seller_status(request, seller_id):
    seller = get_object_or_404(SellerProfile, id=seller_id)
    new_status = request.POST.get("status")

    allowed_statuses = {"approved", "suspended"}
    if new_status not in allowed_statuses:
        messages.error(request, "Invalid seller status.")
        return redirect("sellers_management")

    old_status = seller.status
    if new_status == "approved" and seller.is_small_seller and not seller.kyc_complete:
        messages.error(request, "Review Aadhaar identity, the small-seller declaration and bank details before approving this small seller.")
        return redirect("sellers_management")
    if new_status == "approved" and seller.business_segment not in dict(SellerProfile.BUSINESS_SEGMENTS):
        messages.error(request, "Select a valid selling segment in Django admin before approving this seller.")
        return redirect("sellers_management")
    seller.status = new_status
    seller.save(update_fields=["status", "updated_at"])
    audit(request, "seller.status", seller, f"Seller {seller.store_name}: {old_status} → {new_status}")

    if new_status == "approved":
        messages.success(request, f"{seller.store_name} is now approved to sell.")
    else:
        messages.warning(request, f"{seller.store_name} has been suspended.")

    return redirect("sellers_management")


@operations_admin_required
def seller_aadhaar_image(request, seller_id):
    from pathlib import Path
    from django.http import FileResponse, Http404
    seller = get_object_or_404(SellerProfile, pk=seller_id, registration_type="small")
    if not seller.aadhaar_image or not seller.aadhaar_consent_at:
        raise Http404
    try:
        document = seller.aadhaar_image.open("rb")
    except FileNotFoundError:
        raise Http404
    audit(request, "seller.aadhaar_image_viewed", seller, "Admin viewed seller identity document.")
    response = FileResponse(document, filename="aadhaar" + Path(seller.aadhaar_image.name).suffix)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@require_POST
@operations_admin_required
@transaction.atomic
def review_small_seller(request, seller_id):
    from accounts.forms import SmallSellerReviewForm
    seller = get_object_or_404(SellerProfile.objects.select_for_update(), pk=seller_id, registration_type="small")
    if request.POST.get("decision") not in {"verified", "needs_changes"}:
        messages.error(request, "Choose a valid review decision.")
        return redirect("ops_seller_detail", seller_id=seller.pk)
    if request.POST.get("decision") == "needs_changes":
        note = request.POST.get("note", "").strip()[:1000]
        if not note:
            messages.error(request, "Explain what the seller needs to correct.")
            return redirect("ops_seller_detail", seller_id=seller.pk)
        seller.identity_status = "needs_changes"
        seller.identity_review_note = note
        seller.identity_verified_at = None
        seller.identity_verified_by = None
        seller.identity_review_reference = ""
        seller.status = "suspended" if seller.status == "approved" else "pending"
        seller.payouts_enabled = False
    else:
        if not seller.aadhaar_image:
            messages.error(request, "Ask the seller to upload a masked Aadhaar photo before reviewing.")
            return redirect("ops_seller_detail", seller_id=seller.pk)
        form = SmallSellerReviewForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Confirm both identity and business eligibility checks and enter a valid review reference.")
            return redirect("ops_seller_detail", seller_id=seller.pk)
        seller.identity_status = "verified"
        seller.identity_verified_at = timezone.now()
        seller.identity_verified_by = request.user
        seller.identity_review_reference = form.cleaned_data["reference"]
        seller.identity_review_note = ""
        if not seller.kyc_complete:
            messages.error(request, "Application details or Aadhaar consent are incomplete. Ask the seller to resubmit.")
            return redirect("ops_seller_detail", seller_id=seller.pk)
    seller.save()
    audit(request, "seller.small_identity_review", seller, f"Small seller identity review: {seller.identity_status}", reference=seller.identity_review_reference)
    messages.success(request, "Review saved. Seller approval and payout activation remain separate steps.")
    return redirect("ops_seller_detail", seller_id=seller.pk)


@require_POST
@operations_admin_required
def verify_seller_payouts(request, seller_id):
    seller = get_object_or_404(SellerProfile, id=seller_id)
    if not seller.kyc_complete:
        messages.error(request, "KYC is incomplete. Review legal identity, GSTIN for registered sellers or the declaration for small sellers, Aadhaar and bank details first.")
    elif not seller.razorpay_contact_id or not seller.razorpay_fund_account_id:
        messages.error(request, "RazorpayX payout account is missing. Ask the seller to resubmit bank details once.")
    else:
        seller.status = "approved"
        seller.payouts_enabled = True
        seller.save(update_fields=["status", "payouts_enabled", "updated_at"])
        audit(request, "seller.payouts_enabled", seller, f"Enabled payouts for {seller.store_name}")
        messages.success(request, f"{seller.store_name} is verified and automatic payouts are enabled.")
    return redirect("sellers_management")


# ✅ Local Orders page
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def local_orders_list(request):
    local_orders = (
        Order.objects.filter(pincode="243638")
        .exclude(status="Pending")
        .order_by("-created_at")
    )
    return render(request, "dashboard/local_orders.html", {"local_orders": local_orders})


# ✅ Shipping Orders page
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def shipping_orders_list(request):
    shipping_orders = (
        Order.objects.exclude(pincode="243638")
        .exclude(status="Pending")
        .order_by("-created_at")
    )
    return render(request, "dashboard/shipping_orders.html", {"shipping_orders": shipping_orders})


# ✅ Mark order as shipped
@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def mark_order_shipped(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == "POST":
        order.status = "Shipped"
        order.save()

    return redirect(request.META.get("HTTP_REFERER", "admin_dashboard"))


# ✅ Add Category
@operations_admin_required
def add_category(request):
    if request.method == "POST":
        name = request.POST.get("name")
        Category.objects.create(name=name, slug=slugify(name))
        return redirect("admin_dashboard")
    return render(request, "dashboard/add_category.html")


# ✅ Delete Category
@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)
    category.delete()
    messages.success(request, "Category deleted successfully.")
    return redirect("admin_dashboard")



# ✅ Add SubCategory
@operations_admin_required
def add_subcategory(request):
    categories = Category.objects.all()
    if request.method == "POST":
        name = request.POST.get("name")
        category_id = request.POST.get("category")
        category = get_object_or_404(Category, id=category_id)
        SubCategory.objects.create(name=name, category=category)
        return redirect("admin_dashboard")
    return render(request, "dashboard/add_subcategory.html", {"categories": categories})


# ✅ Delete SubCategory
@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def delete_subcategory(request, id):
    subcategory = get_object_or_404(SubCategory, id=id)
    subcategory.delete()
    messages.success(request, "Subcategory deleted successfully.")
    return redirect("admin_dashboard")




@transaction.atomic
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def add_product(request):

    audience_form = ProductAudienceForm(request.POST or None)
    if request.method == "POST" and not audience_form.is_valid():
        return render(request, "dashboard/add_product.html", {
            "categories": Category.objects.all(), "subcategories": SubCategory.objects.all(),
            "audience_form": audience_form,
        }, status=400)
    categories = Category.objects.all().order_by("name")

    subcategories = (
        SubCategory.objects
        .select_related("category")
        .order_by("name")
    )

    # -----------------------------
    # SHOW FORM
    # -----------------------------
    if request.method != "POST":

        return render(
            request,
            "dashboard/add_product.html",
            {
                "audience_form": audience_form,
                "categories": categories,
                "subcategories": subcategories,
            },
        )

    # -----------------------------
    # BASIC PRODUCT DATA
    # -----------------------------

    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    category_id = request.POST.get("category")
    subcategory_id = request.POST.get("subcategory")
    product_type = request.POST.get("product_type")
    cover_image = request.FILES.get("image")

    # -----------------------------
    # PRICE
    # -----------------------------

    try:
        price = float(request.POST.get("price", 0))
    except (ValueError, TypeError):

        messages.error(
            request,
            "Please enter a valid product price."
        )

        return redirect("add_product")

    # -----------------------------
    # STOCK
    # -----------------------------

    try:
        stock = int(request.POST.get("stock", 0))
    except (ValueError, TypeError):

        stock = 0

    # -----------------------------
    # VALIDATION
    # -----------------------------

    if not name:

        messages.error(
            request,
            "Product name is required."
        )

        return redirect("add_product")

    if not category_id:

        messages.error(
            request,
            "Please select a category."
        )

        return redirect("add_product")

    category = get_object_or_404(
        Category,
        id=category_id
    )

    subcategory = None

    if subcategory_id:

        subcategory = get_object_or_404(
            SubCategory,
            id=subcategory_id
        )

    # -----------------------------
    # SIZES
    # -----------------------------

    sizes = []

    for size in request.POST.getlist("sizes[]"):

        size = size.strip()

        if size:

            sizes.append(size)

    if not sizes:

        messages.error(
            request,
            "Please add at least one size."
        )

        return redirect("add_product")

    # -----------------------------
    # COLORS
    # -----------------------------

    color_names = request.POST.getlist("color_name[]")
    color_hexes = request.POST.getlist("color_hex[]")

    valid_colors = []

    for index, color_name in enumerate(color_names):

        color_name = color_name.strip()

        if not color_name:
            continue

        valid_colors.append({
            "name": color_name,
            "hex": (
                color_hexes[index]
                if index < len(color_hexes)
                else "#000000"
            ),
            "index": index,
        })

    if not valid_colors:

        messages.error(
            request,
            "Please add at least one color."
        )

        return redirect("add_product")

    # -----------------------------
    # CREATE PRODUCT
    # -----------------------------

    product = Product.objects.create(
        name=name,
        description=description,
        price=price,
        stock=stock,
        category=category,
        subcategory=subcategory,
        product_type=product_type,
        gender=audience_form.cleaned_data["gender"],
        kids_age_group=audience_form.cleaned_data["kids_age_group"],
        available_sizes=sizes,
        image=cover_image,
        is_active=True,
    )

    # -----------------------------
    # CONTINUE IN PART 2
    # -----------------------------
        # -----------------------------
    # CREATE COLORS
    # -----------------------------

    created_colors = []

    for display_order, color_data in enumerate(valid_colors):

        color = ProductColor.objects.create(
            product=product,
            name=color_data["name"],
            hex_code=color_data["hex"],
            display_order=display_order,
        )

        created_colors.append(color)

        # -----------------------------
        # GALLERY IMAGES
        # -----------------------------

        gallery_images = request.FILES.getlist(
            f"color_gallery_{color_data['index']}"
        )

        first_image = None

        for image_order, image in enumerate(gallery_images):

            product_image = ProductImage.objects.create(
                product=product,
                color=color,
                image=image,
                display_order=image_order,
            )

            if image_order == 0:
                first_image = product_image.image

        # Set first gallery image as color image

        if first_image:

            color.image = first_image
            color.save(update_fields=["image"])

    # -----------------------------
    # CREATE VARIANTS
    # -----------------------------

    stocks = request.POST.getlist("stocks[]")

    for color in created_colors:

        for size_index, size in enumerate(sizes):

            try:
                variant_stock = int(stocks[size_index])

            except (IndexError, ValueError, TypeError):

                variant_stock = 0

            ProductVariant.objects.create(
                product=product,
                color=color,
                size=size,
                stock=variant_stock,
                is_active=True,
            )

    # -----------------------------
    # SUCCESS
    # -----------------------------

    messages.success(
        request,
        f'"{product.name}" added successfully.'
    )

    return redirect("products_management")

# ✅ Delete Product
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def delete_product(request, id):

    product = get_object_or_404(Product, id=id)

    if request.method == "POST":

        if OrderItem.objects.filter(product=product).exists():
            messages.error(
                request,
                f'"{product.name}" cannot be deleted because it has been ordered.'
            )
            return redirect("products_management")

        product.delete()

        messages.success(
            request,
            f'"{product.name}" deleted successfully.'
        )

        return redirect("products_management")

    return render(
        request,
        "dashboard/confirm_delete_product.html",
        {
            "product": product,
        },
    )

@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def toggle_product_status(request, id):

    product = get_object_or_404(Product, id=id)

    if product.seller_id and product.moderation_status != Product.MODERATION_APPROVED:
        messages.error(request, "Review this seller listing before making it live.")
        return redirect("products_management")

    product.is_active = not product.is_active
    product.save()

    if product.is_active:
        messages.success(
            request,
            f"{product.name} has been activated."
        )
    else:
        messages.success(
            request,
            f"{product.name} has been deactivated."
        )

    return redirect("products_management")


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
@require_POST
def review_seller_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller__isnull=False)
    action = request.POST.get("action")
    reason = request.POST.get("reason", "").strip()
    if action == "approve":
        product.moderation_status = Product.MODERATION_APPROVED
        product.is_active = True
        product.rejection_reason = ""
        message = f'"{product.name}" approved and published.'
    elif action == "reject":
        if not reason:
            messages.error(request, "Add a reason before rejecting the product.")
            return redirect("products_management")
        product.moderation_status = Product.MODERATION_REJECTED
        product.is_active = False
        product.rejection_reason = reason
        message = f'"{product.name}" rejected and kept private.'
    else:
        messages.error(request, "Invalid product review action.")
        return redirect("products_management")
    product.reviewed_by = request.user
    product.reviewed_at = timezone.now()
    product.save(update_fields=["moderation_status", "is_active", "rejection_reason", "reviewed_by", "reviewed_at"])
    messages.success(request, message)
    return redirect("products_management")


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def catalog_requests_management(request):
    catalog_requests = CatalogRequest.objects.select_related(
        "seller", "seller__user", "parent_category", "reviewed_by"
    )
    return render(request, "dashboard/catalog_requests_management.html", {"catalog_requests": catalog_requests})


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
@require_POST
@transaction.atomic
def review_catalog_request(request, request_id):
    catalog_request = get_object_or_404(CatalogRequest, id=request_id)
    action = request.POST.get("action")
    note = request.POST.get("admin_note", "").strip()
    if catalog_request.status != CatalogRequest.STATUS_PENDING:
        messages.info(request, "This catalog request has already been reviewed.")
        return redirect("catalog_requests_management")
    if action == "approve":
        if catalog_request.request_type == CatalogRequest.TYPE_CATEGORY:
            existing = _matching_category(catalog_request.name)
            if existing is None:
                Category.objects.create(name=catalog_request.name)
        else:
            existing = _matching_subcategory(
                catalog_request.parent_category, catalog_request.name
            )
            if existing is None:
                SubCategory.objects.create(
                    category=catalog_request.parent_category,
                    name=catalog_request.name,
                )
        catalog_request.status = CatalogRequest.STATUS_APPROVED
        if existing:
            duplicate_note = (
                f'Not created again because "{existing.name}" already exists.'
            )
            catalog_request.admin_note = " ".join(
                part for part in (note, duplicate_note) if part
            )
            messages.info(request, duplicate_note)
        else:
            catalog_request.admin_note = note
            messages.success(request, "Catalog request approved and added to the storefront catalog.")
    elif action == "reject":
        if not note:
            messages.error(request, "Add an admin note before rejecting this request.")
            return redirect("catalog_requests_management")
        catalog_request.status = CatalogRequest.STATUS_REJECTED
        messages.success(request, "Catalog request rejected.")
    else:
        messages.error(request, "Invalid catalog review action.")
        return redirect("catalog_requests_management")
    if action == "reject":
        catalog_request.admin_note = note
    catalog_request.reviewed_by = request.user
    catalog_request.reviewed_at = timezone.now()
    catalog_request.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at"])
    return redirect("catalog_requests_management")


@require_POST
@operations_admin_required
def ajax_add_category(request):

    if request.method == "POST":

        data = json.loads(request.body)

        name = data.get("name", "").strip()

        if not name:
            return JsonResponse({
                "success": False
            })

        category, created = Category.objects.get_or_create(
            name=name,
            defaults={
                "slug": slugify(name)
            }
        )

        return JsonResponse({
            "success": True,
            "id": category.id,
            "name": category.name
        })

    return JsonResponse({
        "success": False
    })


@require_POST
@operations_admin_required
def ajax_add_subcategory(request):

    if request.method == "POST":

        data = json.loads(request.body)

        name = data.get("name", "").strip()

        category_id = data.get("category")

        if not name or not category_id:

            return JsonResponse({
                "success": False
            })

        category = get_object_or_404(
            Category,
            id=category_id
        )

        subcategory, created = SubCategory.objects.get_or_create(
            name=name,
            category=category
        )

        return JsonResponse({

            "success": True,

            "id": subcategory.id,

            "name": subcategory.name

        })

    return JsonResponse({

        "success": False

    })



@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def products_management(request):

    products = (
        Product.objects
        .select_related("category", "subcategory", "seller", "seller__user")
        .order_by("-created")
    )

    return render(
        request,
        "dashboard/products_management.html",
        {
            "products": products,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def categories_management(request):

    categories = Category.objects.all()

    return render(
        request,
        "dashboard/categories_management.html",
        {
            "categories": categories,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def subcategories_management(request):

    subcategories = (
        SubCategory.objects
        .select_related("category")
    )

    return render(
        request,
        "dashboard/subcategories_management.html",
        {
            "subcategories": subcategories,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def inventory_management(request):

    variants = (
        ProductVariant.objects
        .select_related("product", "color")
        .order_by("product__name")
    )

    return render(
        request,
        "dashboard/inventory_management.html",
        {
            "variants": variants,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def customers_management(request):

    customers = (
        User.objects
        .filter(is_superuser=False)
        .order_by("-date_joined")
    )

    return render(
        request,
        "dashboard/customers_management.html",
        {
            "customers": customers,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def reviews_management(request):

    reviews = (
        ProductReview.objects
        .select_related("user", "product")
        .order_by("-created_at")
    )

    return render(
        request,
        "dashboard/reviews_management.html",
        {
            "reviews": reviews,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def returns_management(request):

    returns = (
        ReturnRequest.objects
        .select_related(
            "user",
            "order",
            "order_item",
        )
        .order_by("-created_at")
    )

    search = request.GET.get("search")
    status = request.GET.get("status")
    refund = request.GET.get("refund")

    if search:

        returns = returns.filter(

            Q(id__icontains=search) |

            Q(order__id__icontains=search) |

            Q(user__username__icontains=search) |

            Q(user__email__icontains=search) |

            Q(order_item__product_name__icontains=search)

        )

    if status:

        returns = returns.filter(status=status)

    if refund:

        returns = returns.filter(refund_status=refund)

    # -------------------------
    # Pagination
    # -------------------------

    paginator = Paginator(returns, 10)

    page_number = request.GET.get("page")

    returns = paginator.get_page(page_number)

    context = {

        "returns": returns,

        "total_requests": ReturnRequest.objects.count(),

        "pending_requests": ReturnRequest.objects.filter(
            status="Pending"
        ).count(),

        "approved_requests": ReturnRequest.objects.filter(
            status="Approved"
        ).count(),

        "rejected_requests": ReturnRequest.objects.filter(
            status="Rejected"
        ).count(),

        "refund_pending": ReturnRequest.objects.filter(
            refund_status="Pending"
        ).count(),

        "refund_processed": ReturnRequest.objects.filter(
            refund_status="Processed"
        ).count(),
    }

    return render(
        request,
        "dashboard/returns_management.html",
        context,
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def support_management(request):

    tickets = (
        SupportTicket.objects
        .select_related("user", "user__profile", "order")
        .order_by("-created_at")
    )

    # -------------------------
    # Search
    # -------------------------

    search = request.GET.get("search", "").strip()

    if search:

        tickets = tickets.filter(

            Q(id__icontains=search) |

            Q(subject__icontains=search) |

            Q(message__icontains=search) |

            Q(user__username__icontains=search) |

            Q(user__first_name__icontains=search) |

            Q(user__last_name__icontains=search) |

            Q(user__email__icontains=search) |

            Q(order__id__icontains=search)

        )

    # -------------------------
    # Status Filter
    # -------------------------

    status = request.GET.get("status", "").strip()

    if status:

        tickets = tickets.filter(status=status)

    # -------------------------
    # Read Filter
    # -------------------------

    read = request.GET.get("read", "").strip()

    if read == "Unread":

        tickets = tickets.filter(is_read=False)

    elif read == "Read":

        tickets = tickets.filter(is_read=True)

    # -------------------------
    # Pagination
    # -------------------------

    paginator = Paginator(tickets, 10)

    page_number = request.GET.get("page")

    tickets = paginator.get_page(page_number)

    context = {

        "tickets": tickets,

        "search": search,

        "selected_status": status,

        "selected_read": read,

        # Summary Cards

        "total_tickets": SupportTicket.objects.count(),

        "open_tickets": SupportTicket.objects.filter(
            status="Open"
        ).count(),

        "progress_tickets": SupportTicket.objects.filter(
            status="In Progress"
        ).count(),

        "resolved_tickets": SupportTicket.objects.filter(
            status="Resolved"
        ).count(),

        "unread_tickets": SupportTicket.objects.filter(
            is_read=False
        ).count(),

    }

    return render(
        request,
        "dashboard/support_management.html",
        context,
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def analytics_dashboard(request):

    monthly_sales = list(
        Order.objects.filter(payment_status="Paid")
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("total_price"))
        .order_by("month")
    )

    top_products = (
        OrderItem.objects
        .values("product_name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")[:5]
    )

    latest_orders = (
        Order.objects
        .select_related("user")
        .order_by("-created_at")[:10]
    )

    context = {

        "total_orders": Order.objects.count(),

        "total_revenue":
            Order.objects.filter(payment_status="Paid")
            .aggregate(total=Sum("total_price"))["total"] or 0,

        "total_customers":
            User.objects.filter(is_superuser=False).count(),

        "total_products":
            Product.objects.count(),

        "pending_orders":
            Order.objects.filter(status="Pending").count(),

        "processing_orders":
            Order.objects.filter(status="Processing").count(),

        "packed_orders":
            Order.objects.filter(status="Packed").count(),

        "shipped_orders":
            Order.objects.filter(status="Shipped").count(),

        "delivered_orders":
            Order.objects.filter(status="Delivered").count(),

        "cancelled_orders":
            Order.objects.filter(status="Cancelled").count(),

        "returned_orders":
            Order.objects.filter(status="Returned").count(),

        "monthly_sales": monthly_sales,

        "top_products": top_products,

        "latest_orders": latest_orders,
    }

    return render(
        request,
        "dashboard/analytics_dashboard.html",
        context,
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def order_management(request):

    orders = (
        Order.objects
        .select_related("user")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    # Search
    search = request.GET.get("search", "").strip()

    if search:
        orders = orders.filter(
            Q(id__icontains=search) |
            Q(full_name__icontains=search) |
            Q(phone__icontains=search) |
            Q(city__icontains=search) |
            Q(user__username__icontains=search)
        )

    # Order Status Filter
    status = request.GET.get("status", "").strip()

    if status:
        orders = orders.filter(status=status)

    # Payment Status Filter
    payment = request.GET.get("payment", "").strip()

    if payment:
        orders = orders.filter(payment_status=payment)



    today = timezone.localdate()

    context = {
        "orders": orders,

        "search": search,
        "selected_status": status,
        "selected_payment": payment,

        # Main Statistics
        "total_orders": Order.objects.count(),

        "new_orders": Order.objects.filter(
            is_new=True
        ).count(),

        "pending": Order.objects.filter(
            status="Pending"
        ).count(),

        "processing": Order.objects.filter(
            status="Processing"
        ).count(),

        "packed": Order.objects.filter(
            status="Packed"
        ).count(),

        "shipped": Order.objects.filter(
            status="Shipped"
        ).count(),

        "out_for_delivery": Order.objects.filter(
            status="Out for Delivery"
        ).count(),

        "delivered": Order.objects.filter(
            status="Delivered"
        ).count(),

        "cancelled": Order.objects.filter(
            status="Cancelled"
        ).count(),

        "returned": Order.objects.filter(
            status="Returned"
        ).count(),

        # Today's Activity
        "today_orders": Order.objects.filter(
            created_at__date=today
        ).count(),

        "today_revenue": (
            Order.objects.filter(
                created_at__date=today,
                payment_status="Paid"
            ).aggregate(
                total=Sum("total_price")
            )["total"] or 0
        ),

        # Orders Needing Action
        "action_required": Order.objects.filter(
            status__in=[
                "Pending",
                "Processing",
                "Packed",
            ]
        ).count(),

        # High Value Orders
        "high_value_orders": Order.objects.filter(
            total_price__gte=5000
        ).count(),
    }
    return render(
    request,
    "dashboard/orders_management.html",
    context,
)

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def order_detail_ajax(request, order_id):

    order = get_object_or_404(
        Order.objects.select_related("user")
        .prefetch_related(
            "items",
            "items__product",
            "items__variant",
        ),
        id=order_id,
    )

    html = render_to_string(
        "dashboard/includes/order_detail_modal.html",
        {
            "order": order,
        },
        request=request,
    )

    return JsonResponse({
        "html": html
    })


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def update_order_status(request, order_id):

    order = get_object_or_404(Order, id=order_id)

    new_status = request.POST.get("status")
    payment_status = request.POST.get("payment_status")
    old_status = order.status
    old_payment_status = order.payment_status

    valid_flow = {
        "Pending": ["Processing", "Cancelled"],
        "Processing": ["Packed", "Cancelled"],
        "Packed": ["Shipped", "Cancelled"],
        "Shipped": ["Out for Delivery"],
        "Out for Delivery": ["Delivered"],
        "Delivered": ["Returned"],
        "Cancelled": [],
        "Returned": [],
    }
    valid_payment_statuses = {choice[0] for choice in Order.PAYMENT_STATUS_CHOICES}
    if new_status != old_status and new_status not in valid_flow.get(old_status, []):
        messages.error(request, f"Order cannot move from {old_status} to {new_status}.")
        return redirect("orders_management")
    if payment_status not in valid_payment_statuses:
        messages.error(request, "Invalid payment status.")
        return redirect("orders_management")

    # Remove the new badge after the first valid admin action.
    if order.is_new:
        order.is_new = False

    if (
            order.status == "Pending"
            and new_status == "Processing"
    ):
        order.confirmed_at = timezone.now()
        order.confirmed_by = request.user

    elif (
            order.status == "Processing"
            and new_status == "Packed"
    ):
        order.packed_at = timezone.now()

    elif (
            order.status == "Packed"
            and new_status == "Shipped"
    ):
        order.shipped_at = timezone.now()

    elif (
            order.status == "Shipped"
            and new_status == "Out for Delivery"
    ):
        order.out_for_delivery_at = timezone.now()

    elif (
            order.status == "Out for Delivery"
            and new_status == "Delivered"
    ):
        order.delivered_at = timezone.now()

    elif new_status == "Cancelled":
        order.cancelled_at = timezone.now()
    order.status = new_status
    order.payment_status = payment_status

    order.save()

    if new_status == "Packed":
        from orders.pickups import queue_order_pickups
        queue_order_pickups(order.pk)

    from orders.settlements import create_settlements_for_order
    create_settlements_for_order(order)

    # -------------------------------
    # ORDER TIMELINE
    # -------------------------------

    if old_status != new_status:

        event_map = {
            "Processing": "Order Confirmed",
            "Packed": "Packed",
            "Shipped": "Shipped",
            "Out for Delivery": "Out for Delivery",
            "Delivered": "Delivered",
            "Cancelled": "Cancelled",
            "Returned": "Returned",
        }

        OrderTimeline.objects.create(
            order=order,
            event=event_map.get(new_status, new_status),
            description=f"Order status changed from {old_status} to {new_status}.",
            performed_by=request.user,
        )

        from orders.emails import send_order_status_email
        send_order_status_email(order, old_status)

    audit(
        request,
        "order.update",
        order,
        f"Parcel order #{order.pk} updated",
        old_status=old_status,
        new_status=new_status,
        old_payment_status=old_payment_status,
        new_payment_status=payment_status,
    )
    messages.success(request, "Order updated successfully.")

    return redirect("orders_management")

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def download_invoice(request, order_id):
    # Keep optional PDF dependencies out of normal dashboard page imports.
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle


    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        id=order_id
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Invoice-{order.id}.pdf"'

    doc = SimpleDocTemplate(response)
    styles = getSampleStyleSheet()

    elements = []

    elements.append(Paragraph("<b>ZIYAMART FASHION</b>", styles["Title"]))
    elements.append(Paragraph(f"Invoice #{order.id}", styles["Heading2"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    elements.append(Paragraph(f"<b>Customer:</b> {order.full_name}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Phone:</b> {order.phone}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Address:</b> {order.address}", styles["Normal"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    data = [["Product", "Qty", "Price", "Total"]]

    for item in order.items.all():

        data.append([
            item.product_name,
            item.quantity,
            f"₹{item.price}",
            f"₹{item.price * item.quantity}"
        ])

    data.append(["", "", "Grand Total", f"₹{order.total_price}"])

    table = Table(data, colWidths=[3*inch, .8*inch, 1*inch, 1.2*inch])

    table.setStyle(TableStyle([

        ("BACKGROUND",(0,0),(-1,0),colors.black),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),1,colors.grey),
        ("BACKGROUND",(0,1),(-1,-1),colors.beige),
        ("BOTTOMPADDING",(0,0),(-1,0),10),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

    ]))

    elements.append(table)

    doc.build(elements)

    return response
from django.utils.text import slugify

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def edit_product(request, id):

    product = get_object_or_404(Product, id=id)
    audience_form = ProductAudienceForm(request.POST or None, instance=product)
    if request.method == "POST" and not audience_form.is_valid():
        return render(request, "dashboard/edit_product.html", {
            "product": product, "categories": Category.objects.all(),
            "subcategories": SubCategory.objects.all(), "audience_form": audience_form,
        }, status=400)

    categories = Category.objects.all()
    subcategories = SubCategory.objects.all()

    if request.method == "POST":

        old_name = product.name

        product.name = request.POST.get("name", "").strip()
        product.description = request.POST.get("description", "").strip()
        product.price = request.POST.get("price")
        product.stock = request.POST.get("stock")

        product.category = get_object_or_404(
            Category,
            id=request.POST.get("category")
        )

        subcategory_id = request.POST.get("subcategory")

        if subcategory_id:
            product.subcategory = get_object_or_404(
                SubCategory,
                id=subcategory_id
            )
        else:
            product.subcategory = None

        product.product_type = request.POST.get("product_type")
        product.gender = audience_form.cleaned_data["gender"]
        product.kids_age_group = audience_form.cleaned_data["kids_age_group"]

        # Only regenerate the slug if the product name changed
        if product.name != old_name:

            base_slug = slugify(product.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(slug=slug).exclude(id=product.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            product.slug = slug

        if request.FILES.get("image"):
            product.image = request.FILES["image"]

        product.save()

        messages.success(
            request,
            "Product updated successfully."
        )

        return redirect("products_management")

    return render(
        request,
        "dashboard/edit_product.html",
        {
            "product": product,
            "audience_form": audience_form,
            "categories": categories,
            "subcategories": subcategories,
        },
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def edit_inventory(request, id):

    variant = get_object_or_404(
        ProductVariant,
        id=id
    )

    if request.method == "POST":

        variant.stock = request.POST.get("stock")

        variant.sku = request.POST.get("sku")

        variant.is_active = (
            True if request.POST.get("is_active") else False
        )

        variant.save()


        messages.success(
            request,
            "Inventory updated successfully."
        )

        return redirect(
            "inventory_management"
        )


    return render(
        request,
        "dashboard/edit_inventory.html",
        {
            "variant": variant
        }
    )


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def approve_review(request, id):

    review = get_object_or_404(ProductReview, id=id)

    review.is_approved = True
    review.save()

    messages.success(
        request,
        "Review approved successfully."
    )

    return redirect("reviews_management")


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def delete_review(request, id):

    review = get_object_or_404(ProductReview, id=id)

    review.delete()

    messages.success(
        request,
        "Review deleted successfully."
    )

    return redirect("reviews_management")

@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
@transaction.atomic
def approve_return(request, return_id):

    return_request = get_object_or_404(
        ReturnRequest,
        id=return_id
    )

    # Prevent processing the same request twice
    if return_request.status != "Pending":

        messages.warning(
            request,
            "This return request has already been processed."
        )

        return redirect("returns_management")

    if request.method == "POST":

        # -------------------------
        # Update Return Request
        # -------------------------

        requested_refund_status = request.POST.get("refund_status", "Pending")
        if requested_refund_status == "Processed" and return_request.order.payment_method == "online":
            try:
                from payments.services import request_refund
                refund_amount = return_request.order_item.total if return_request.order_item else return_request.order.total_price
                request_refund(
                    return_request.order,
                    refund_amount,
                    f"Approved return #{return_request.pk}",
                )
            except Exception as exc:
                messages.error(request, f"Return remains pending because the refund could not be submitted: {exc}")
                return redirect("returns_management")
        return_request.status = "Completed" if requested_refund_status == "Processed" else "Approved"

        return_request.admin_note = request.POST.get(
            "admin_note",
            ""
        )

        return_request.refund_status = requested_refund_status

        return_request.save()

        if return_request.refund_status == "Processed":
            from orders.settlements import create_return_debit
            create_return_debit(return_request)

        # -------------------------
        # Restock Only Returned Item
        # -------------------------

        returned_item = return_request.order_item

        if returned_item:

            if returned_item.variant:

                returned_item.variant.stock += returned_item.quantity
                returned_item.variant.save()

            elif returned_item.product:

                returned_item.product.stock += returned_item.quantity
                returned_item.product.save()

        # -------------------------
        # Update Order Status
        # -------------------------

        order = return_request.order

        total_items = order.items.count()

        approved_returns = ReturnRequest.objects.filter(
            order=order,
            status="Approved"
        ).count()

        if total_items > 0 and approved_returns >= total_items:

            order.status = "Returned"
            order.save()

        messages.success(
            request,
            "Return approved and inventory updated."
        )

    return redirect("returns_management")

@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def reject_return(request, return_id):

    return_request = get_object_or_404(
        ReturnRequest,
        id=return_id
    )

    if request.method == "POST":

        return_request.status = "Rejected"

        return_request.admin_note = request.POST.get(
            "admin_note",
            ""
        )

        return_request.refund_status = "Rejected"

        return_request.save()

        messages.success(
            request,
            "Return request rejected."
        )

    return redirect("returns_management")


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def support_ticket_detail(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket.objects.select_related(
            "user",
            "order",
        ),
        id=ticket_id,
    )

    replies = (
        ticket.replies
        .select_related("user")
        .all()
    )

    if not ticket.is_read:
        ticket.is_read = True
        ticket.save(update_fields=["is_read"])

    return render(
        request,
        "dashboard/support_ticket_detail.html",
        {
            "ticket": ticket,
            "replies": replies,
        },
    )


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def reply_support_ticket(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket,
        id=ticket_id,
    )

    if request.method == "POST":

        message = request.POST.get("message", "").strip()

        if message:

            SupportReply.objects.create(
                ticket=ticket,
                user=request.user,
                message=message,
                is_staff=True,
            )

            ticket.last_reply_at = timezone.now()
            ticket.status = "In Progress"
            ticket.save()

            messages.success(
                request,
                "Reply sent successfully."
            )

            # Email notification will be added later.

    return redirect(
        "support_ticket_detail",
        ticket_id=ticket.id,
    )


@require_POST
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def update_support_status(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket,
        id=ticket_id,
    )

    if request.method == "POST":

        ticket.status = request.POST.get(
            "status",
            ticket.status,
        )

        ticket.admin_note = request.POST.get(
            "admin_note",
            "",
        )

        ticket.save()

        messages.success(
            request,
            "Ticket updated successfully."
        )

    return redirect(
        "support_ticket_detail",
        ticket_id=ticket.id,
    )


@login_required
def seller_add_electronics(request, kind):
    from products.electronics import ELECTRONICS
    from .electronics import ElectronicsProductForm
    if kind not in ELECTRONICS:
        from django.http import Http404
        raise Http404
    seller = _merchandise_seller_for(request)
    from products.electronics import seller_electronics_types
    if kind not in seller_electronics_types(seller):
        raise PermissionDenied("This product category is not part of your seller catalog.")
    form = ElectronicsProductForm(request.POST or None, request.FILES or None, kind=kind, seller=seller)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            category, _ = Category.objects.get_or_create(slug="electronics", defaults={"name": "Electronics"})
            subcategory, _ = SubCategory.objects.get_or_create(category=category, name=ELECTRONICS[kind]["name"])
            product = form.save(commit=False)
            product.category, product.subcategory, product.seller = category, subcategory, seller
            product.is_active = False
            product.moderation_status = Product.MODERATION_PENDING
            product.save()
            color = ProductColor.objects.create(product=product, name=form.cleaned_data["color"])
            ProductVariant.objects.create(product=product, color=color, size="Standard", stock=product.stock)
        messages.success(request, "Electronics product submitted for marketplace review.")
        return redirect("seller_products")
    return render(request, "dashboard/seller/electronics_product.html", {"seller": seller, "form": form, "kind": ELECTRONICS[kind]})
