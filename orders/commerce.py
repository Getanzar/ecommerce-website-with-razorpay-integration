from decimal import Decimal

import razorpay
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from addresses.models import Address
from cart.cart import Cart
from payments.models import PaymentTransaction
from payments.pricing import DeliveryQuoteError, build_parcel_pricing, line_charges, money
from payments.services import create_breakdown, create_seller_delivery_charges
from products.catalog import sellable_variants
from products.models import Product, ProductVariant

from .emails import send_order_confirmation_email
from .forms import CheckoutForm
from .models import Order, OrderItem, OrderTimeline


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _snapshot(cart_items, checkout_data, pricing, quotes):
    items = []
    for row in cart_items:
        charges = line_charges(
            row["variant"].seller_price,
            row["variant"].final_price,
            row["quantity"],
            row["product"].gst_rate,
        )
        items.append({
            "product_id": row["product"].pk,
            "variant_id": row["variant"].pk,
            "quantity": row["quantity"],
            "seller_unit_price": str(row["variant"].seller_price),
            "customer_unit_price": str(row["variant"].final_price),
            **{key: str(value) for key, value in charges.items()},
        })
    serialized_quotes = []
    for quote in quotes:
        row = {key: value for key, value in quote.items() if key != "seller"}
        row["seller_id"] = quote["seller"].pk if quote["seller"] else None
        serialized_quotes.append(_json_value(row))
    checkout = {
        key: (value.isoformat() if hasattr(value, "isoformat") else str(value) if isinstance(value, Decimal) else value)
        for key, value in checkout_data.items()
        if key != "gps_captured_at"
    }
    return {"checkout": checkout, "pricing": _json_value(pricing), "quotes": serialized_quotes, "items": items}


def _pricing_from_snapshot(snapshot):
    monetary = {
        "merchant_subtotal", "platform_fee", "merchandise_gst", "platform_fee_gst",
        "delivery_fee", "delivery_gst", "seller_sponsored_delivery",
        "customer_delivery_charge", "grand_total",
    }
    return {
        key: money(value) if key in monetary else value
        for key, value in snapshot["pricing"].items()
    }


def _quotes_from_snapshot(snapshot):
    from accounts.models import SellerProfile

    decimal_fields = {
        "distance_km", "carrier_amount", "handling_fee", "tax_amount",
        "quoted_total", "customer_collection_amount",
    }
    quotes = []
    for saved in snapshot["quotes"]:
        quote = dict(saved)
        seller_id = quote.pop("seller_id")
        quote["seller"] = SellerProfile.objects.get(pk=seller_id) if seller_id else None
        for field in decimal_fields:
            quote[field] = money(quote.get(field, 0))
        quote["chargeable_weight_grams"] = int(quote.get("chargeable_weight_grams", 0))
        quotes.append(quote)
    return quotes


@transaction.atomic
def finalize_parcel_transaction(payment, provider_payment_id=""):
    payment = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
    if payment.parcel_order_id:
        return payment.parcel_order
    snapshot = payment.snapshot
    checkout_data = snapshot["checkout"]
    pricing = _pricing_from_snapshot(snapshot)
    if payment.amount != pricing["grand_total"]:
        raise ValueError("Stored checkout total does not match the payment amount.")
    order = Order.objects.create(
        user=payment.user,
        full_name=checkout_data["full_name"],
        phone=checkout_data["phone"],
        address=checkout_data["address"],
        city=checkout_data["city"],
        state=checkout_data["state"],
        pincode=checkout_data["pincode"],
        latitude=Decimal(checkout_data["latitude"]),
        longitude=Decimal(checkout_data["longitude"]),
        gps_accuracy_meters=int(checkout_data["gps_accuracy_meters"]),
        gps_verified_at=timezone.now(),
        total_price=pricing["grand_total"],
        status="Processing",
        payment_method=checkout_data["payment_method"],
        payment_status="Paid" if payment.provider == "razorpay" else "Pending",
        razorpay_order_id=payment.provider_order_id or None,
        razorpay_payment_id=provider_payment_id or payment.provider_payment_id or None,
    )
    for saved in snapshot["items"]:
        variant = sellable_variants(
            ProductVariant.objects.select_for_update().select_related("product", "product__seller", "color")
        ).get(
            pk=saved["variant_id"], product_id=saved["product_id"],
        )
        quantity = int(saved["quantity"])
        if variant.stock < quantity:
            raise ValueError(f"{variant.product.name} no longer has enough stock.")
        platform_fee = money(saved["platform_fee"])
        product_tax = money(saved["merchandise_gst"])
        platform_tax = money(saved["platform_fee_gst"])
        OrderItem.objects.create(
            order=order,
            product=variant.product,
            variant=variant,
            product_name=variant.product.name,
            product_image=variant.image or variant.product.image,
            product_color=variant.color.name if variant.color_id else "",
            product_size=variant.size,
            product_sku=variant.sku or "",
            quantity=quantity,
            price=money(saved["customer_unit_price"]),
            seller_unit_price=money(saved["seller_unit_price"]),
            platform_fee_amount=platform_fee,
            product_tax_amount=product_tax,
            platform_fee_tax_amount=platform_tax,
            discount=Decimal("0.00"),
            tax=product_tax + platform_tax,
        )
        variant.stock -= quantity
        variant.save(update_fields=["stock"])
    create_breakdown(order, pricing)
    charges = create_seller_delivery_charges(order, _quotes_from_snapshot(snapshot))
    payment.parcel_order = order
    payment.provider_payment_id = provider_payment_id or payment.provider_payment_id
    payment.status = "captured" if payment.provider == "razorpay" else "created"
    payment.captured_at = timezone.now() if payment.provider == "razorpay" else None
    payment.save(update_fields=["parcel_order", "provider_payment_id", "status", "captured_at", "updated_at"])
    OrderTimeline.objects.create(order=order, event="Order Placed", description="Order and financial snapshots created.", performed_by=payment.user)
    if payment.provider == "razorpay":
        from .settlements import create_settlements_for_order
        create_settlements_for_order(order)
    transaction.on_commit(lambda: _start_fulfilment(order.pk, [charge.pk for charge in charges]))
    return order


def _start_fulfilment(order_id, charge_ids):
    from delivery.services import ensure_parcel_deliveries
    from payments.models import SellerDeliveryCharge
    from .shipping import manifest_delhivery_shipments

    order = Order.objects.get(pk=order_id)
    charges = list(SellerDeliveryCharge.objects.filter(pk__in=charge_ids).select_related("seller"))
    ensure_parcel_deliveries(order, charges)
    manifest_delhivery_shipments(order, charges)
    send_order_confirmation_email(order)


def _quote_cart(request, form):
    items = list(Cart(request))
    destination = {
        "pincode": form.cleaned_data["pincode"],
        "latitude": form.cleaned_data["latitude"],
        "longitude": form.cleaned_data["longitude"],
    }
    return items, *build_parcel_pricing(items, destination, form.cleaned_data["payment_method"])


@login_required
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        return redirect("cart_detail")
    addresses = Address.objects.filter(user=request.user).order_by("-is_default", "-id")
    form = CheckoutForm(request.POST or None, initial={"payment_method": "online"})
    items = list(cart)
    pricing = None
    razorpay_order_id = ""
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["payment_method"] == "cod":
            return redirect("cod_checkout")
        try:
            items, pricing, quotes = _quote_cart(request, form)
            provider = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)).order.create({
                "amount": int(pricing["grand_total"] * 100),
                "currency": "INR",
                "receipt": f"parcel-{request.user.pk}-{int(timezone.now().timestamp())}"[:40],
                "payment_capture": 1,
                "notes": {"channel": "parcel", "user_id": str(request.user.pk)},
            })
            snapshot = _snapshot(items, form.cleaned_data, pricing, quotes)
            payment = PaymentTransaction.objects.create(
                user=request.user,
                channel_name="parcel",
                provider="razorpay",
                provider_order_id=provider["id"],
                amount=pricing["grand_total"],
                snapshot=snapshot,
            )
            request.session["parcel_payment_transaction"] = payment.pk
            razorpay_order_id = provider["id"]
        except DeliveryQuoteError as exc:
            form.add_error(None, str(exc))
    if pricing is None:
        # The payable total does not include seller-sponsored delivery, so this
        # preview can use the marketplace origin until an address is submitted.
        try:
            pricing, _ = build_parcel_pricing(
                items,
                {"pincode": settings.DELHIVERY_ORIGIN_PINCODE, "latitude": None, "longitude": None},
                "online",
            )
        except DeliveryQuoteError:
            pricing = None
    return render(request, "orders/checkout.html", {
        "form": form,
        "addresses": addresses,
        "items": items,
        "subtotal": pricing["merchant_subtotal"] + pricing["platform_fee"] if pricing else cart.get_total_price(),
        "shipping": pricing["delivery_fee"] + pricing["delivery_gst"] if pricing else Decimal("0.00"),
        "tax": pricing["merchandise_gst"] + pricing["platform_fee_gst"] if pricing else Decimal("0.00"),
        "pricing": pricing,
        "amount_display": f"₹{pricing['grand_total']:.2f}" if pricing else "",
        "total_paise": int(pricing["grand_total"] * 100) if pricing else 0,
        "currency": "INR",
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "razorpay_order_id": razorpay_order_id,
    })


@login_required
@require_POST
def payment_success(request):
    provider_order_id = request.POST.get("razorpay_order_id", "")
    provider_payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    payment = None
    try:
        razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)).utility.verify_payment_signature({
            "razorpay_order_id": provider_order_id,
            "razorpay_payment_id": provider_payment_id,
            "razorpay_signature": signature,
        })
        payment = PaymentTransaction.objects.get(
            provider="razorpay", provider_order_id=provider_order_id, user=request.user,
        )
        order = finalize_parcel_transaction(payment, provider_payment_id)
    except (ValueError, ProductVariant.DoesNotExist) as exc:
        if payment is not None:
            payment.provider_payment_id = provider_payment_id
            payment.status = "captured"
            payment.captured_at = timezone.now()
            payment.save(update_fields=["provider_payment_id", "status", "captured_at", "updated_at"])
            try:
                from payments.services import request_payment_refund
                request_payment_refund(payment, payment.amount, f"Parcel checkout failed: {str(exc)[:180]}")
            except Exception:
                payment.failure_reason = f"Automatic refund requires review: {str(exc)[:700]}"
                payment.save(update_fields=["failure_reason", "updated_at"])
        return HttpResponseBadRequest("Payment was captured but the order could not be completed; an automatic refund was requested.")
    except (razorpay.errors.SignatureVerificationError, PaymentTransaction.DoesNotExist):
        return HttpResponseBadRequest("Payment could not be safely matched to this checkout.")
    Cart(request).clear()
    return redirect("order_success", order_id=order.pk)


@login_required
@require_POST
def cod_checkout(request):
    if len(Cart(request)) == 0:
        messages.error(request, "Your cart no longer contains an available product.")
        return redirect("cart_detail")
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Review the address and capture GPS again.")
        return redirect("checkout")
    form.cleaned_data["payment_method"] = "cod"
    try:
        items, pricing, quotes = _quote_cart(request, form)
    except DeliveryQuoteError as exc:
        messages.error(request, str(exc))
        return redirect("checkout")
    snapshot = _snapshot(items, form.cleaned_data, pricing, quotes)
    payment = PaymentTransaction.objects.create(
        user=request.user,
        channel_name="parcel",
        provider="cod",
        amount=pricing["grand_total"],
        snapshot=snapshot,
    )
    try:
        order = finalize_parcel_transaction(payment)
    except (ValueError, ProductVariant.DoesNotExist) as exc:
        messages.error(request, str(exc))
        return redirect("cart_detail")
    Cart(request).clear()
    return redirect("order_success", order_id=order.pk)
