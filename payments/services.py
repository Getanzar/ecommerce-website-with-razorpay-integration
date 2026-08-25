import hashlib
import hmac
import json
from decimal import Decimal

import razorpay
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ChargeBreakdown, PaymentTransaction, PaymentWebhookEvent,
    RefundTransaction, SellerDeliveryCharge,
)
from .pricing import money


def order_link(order):
    from food.models import FoodOrder
    from groceries.models import GroceryOrder
    from orders.models import Order

    if isinstance(order, Order):
        return {"parcel_order": order}
    if isinstance(order, FoodOrder):
        return {"food_order": order}
    if isinstance(order, GroceryOrder):
        return {"grocery_order": order}
    raise TypeError("Unsupported order type")


def channel_for(order):
    return next(key.replace("_order", "") for key in order_link(order))


def create_breakdown(order, pricing):
    defaults = {
        key: pricing[key]
        for key in (
            "merchant_subtotal", "platform_fee", "merchandise_gst", "platform_fee_gst",
            "delivery_fee", "delivery_gst", "seller_sponsored_delivery",
            "customer_delivery_charge", "grand_total", "delivery_mode",
        )
    }
    return ChargeBreakdown.objects.update_or_create(**order_link(order), defaults=defaults)[0]


def create_seller_delivery_charges(order, quotes):
    records = []
    for quote in quotes:
        seller = quote["seller"]
        defaults = {
            "provider": quote["provider"],
            "origin_pincode": quote["origin_pincode"],
            "destination_pincode": quote["destination_pincode"],
            "chargeable_weight_grams": quote["chargeable_weight_grams"],
            "distance_km": quote["distance_km"],
            "carrier_amount": quote["carrier_amount"],
            "handling_fee": quote["handling_fee"],
            "tax_amount": quote["tax_amount"],
            "quoted_total": quote["quoted_total"],
            "final_total": quote["quoted_total"],
            "customer_collection_amount": quote.get("customer_collection_amount", Decimal("0.00")),
            "quote_payload": quote["quote_payload"],
        }
        record, _ = SellerDeliveryCharge.objects.update_or_create(
            seller=seller, **order_link(order), defaults=defaults,
        )
        records.append(record)
    return records


def create_local_seller_delivery_charge(order, seller, origin_pincode, destination_pincode, amount):
    amount = money(amount)
    record, _ = SellerDeliveryCharge.objects.update_or_create(
        seller=seller,
        **order_link(order),
        defaults={
            "provider": "local",
            "origin_pincode": origin_pincode,
            "destination_pincode": destination_pincode,
            "carrier_amount": amount,
            "handling_fee": Decimal("0.00"),
            "tax_amount": Decimal("0.00"),
            "quoted_total": amount,
            "final_total": amount,
            "customer_collection_amount": money(getattr(order, "total_price", getattr(order, "total", 0))),
            "quote_payload": {"tax_policy": "local_delivery_untaxed"},
        },
    )
    return record


def create_payment_transaction(order, provider_order_id="", snapshot=None):
    provider = "cod" if order.payment_method == "cod" else "razorpay"
    transaction_record, _ = PaymentTransaction.objects.update_or_create(
        provider=provider,
        provider_order_id=provider_order_id or "",
        **order_link(order),
        defaults={
            "user": order.user,
            "channel_name": channel_for(order),
            "amount": money(getattr(order, "total_price", getattr(order, "total", 0))),
            "status": "created" if provider == "razorpay" else "created",
            "snapshot": snapshot or {},
        },
    )
    return transaction_record


def create_razorpay_order(amount, receipt, notes):
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return client.order.create({
        "amount": int(money(amount) * 100),
        "currency": "INR",
        "receipt": receipt[:40],
        "notes": notes,
        "payment_capture": 1,
    })


@transaction.atomic
def capture_browser_payment(order, provider_order_id, payment_id, signature):
    params = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    }
    razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)).utility.verify_payment_signature(params)
    payment = PaymentTransaction.objects.select_for_update().filter(
        provider="razorpay", provider_order_id=provider_order_id,
    ).first()
    if payment and payment.provider_payment_id and payment.provider_payment_id != payment_id:
        raise ValueError("This provider order is already associated with another payment.")
    if not payment:
        payment = create_payment_transaction(order, provider_order_id)
    expected = money(getattr(order, "total_price", getattr(order, "total", 0)))
    if payment.amount != expected:
        raise ValueError("Payment amount does not match the order total.")
    payment.provider_payment_id = payment_id
    payment.status = "captured"
    payment.captured_at = timezone.now()
    payment.failure_reason = ""
    for field, value in order_link(order).items():
        setattr(payment, field, value)
    payment.save(update_fields=[
        "provider_payment_id", "status", "captured_at", "failure_reason",
        "parcel_order", "food_order", "grocery_order", "updated_at",
    ])
    return payment


def _sync_order_payment(payment, paid):
    order = payment.order
    if not order and paid and payment.channel_name == "parcel" and payment.snapshot:
        from orders.commerce import finalize_parcel_transaction
        try:
            order = finalize_parcel_transaction(payment, payment.provider_payment_id)
        except Exception as exc:
            # Payment can win a race with stock. Never leave captured money
            # without either an order or an automatic refund attempt.
            request_payment_refund(
                payment, payment.amount,
                f"Checkout could not be finalized: {str(exc)[:160]}",
            )
            payment.failure_reason = str(exc)[:1000]
            payment.save(update_fields=["failure_reason", "updated_at"])
            return
    if not order:
        return
    order.payment_status = "Paid" if paid else "Failed"
    fields = ["payment_status", "updated_at"]
    if paid and hasattr(order, "razorpay_payment_id"):
        order.razorpay_payment_id = payment.provider_payment_id
        fields.append("razorpay_payment_id")
    order.save(update_fields=fields)
    if not paid and payment.channel_name == "grocery" and order.status not in {"cancelled", "delivered"}:
        for item in order.items.select_related("product"):
            item.product.stock += item.quantity
            item.product.save(update_fields=["stock"])
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
    elif not paid and payment.channel_name == "food" and order.status not in {"cancelled", "delivered"}:
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
    if paid:
        if payment.channel_name == "parcel":
            from orders.settlements import create_settlements_for_order
            create_settlements_for_order(order)
        elif payment.channel_name == "food":
            from food.settlements import create_food_settlement
            create_food_settlement(order)
        else:
            from groceries.settlements import create_grocery_settlement
            create_grocery_settlement(order)


def handle_razorpay_event(raw_body, signature, event_id):
    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        raise ValueError("RAZORPAY_WEBHOOK_SECRET is not configured.")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise ValueError("Invalid Razorpay webhook signature.")
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    payload = json.loads(raw_body.decode("utf-8"))
    event_type = payload.get("event", "")
    event, created = PaymentWebhookEvent.objects.get_or_create(
        provider="razorpay", event_id=event_id,
        defaults={"event_type": event_type, "payload_hash": payload_hash},
    )
    if not created and event.payload_hash != payload_hash:
        raise ValueError("A webhook event id was reused with different content.")
    if not created and event.status in {"processed", "ignored"}:
        return event
    try:
        with transaction.atomic():
            event = PaymentWebhookEvent.objects.select_for_update().get(pk=event.pk)
            event_payload = payload.get("payload", {})
            entity = event_payload.get("payment", {}).get("entity", {})
            if event_type in {"payment.captured", "order.paid", "payment.failed"}:
                order_entity = event_payload.get("order", {}).get("entity", {})
                provider_order_id = entity.get("order_id") or order_entity.get("id")
                payment = PaymentTransaction.objects.select_for_update().filter(provider_order_id=provider_order_id).first()
                if payment:
                    amount_paise = entity.get("amount", order_entity.get("amount_paid", 0))
                    amount = money(Decimal(amount_paise) / 100)
                    if amount != payment.amount:
                        raise ValueError("Webhook amount does not match the stored payment amount.")
                    payment.provider_payment_id = entity.get("id", payment.provider_payment_id)
                    paid = event_type in {"payment.captured", "order.paid"} or entity.get("status") == "captured"
                    terminal = payment.status in {"partially_refunded", "refunded"}
                    stale_failure = not paid and payment.status == "captured"
                    if not terminal and not stale_failure:
                        payment.status = "captured" if paid else "failed"
                        payment.failure_reason = "" if paid else entity.get("error_description", "Payment failed")
                        payment.captured_at = timezone.now() if paid else payment.captured_at
                        payment.save(update_fields=["provider_payment_id", "status", "failure_reason", "captured_at", "updated_at"])
                        _sync_order_payment(payment, paid)
            elif event_type.startswith("refund."):
                entity = event_payload.get("refund", {}).get("entity", {})
                refund = RefundTransaction.objects.select_for_update().filter(provider_refund_id=entity.get("id", "")).first()
                if refund:
                    refund.status = "processed" if entity.get("status") == "processed" else "failed"
                    refund.failure_reason = "" if refund.status == "processed" else entity.get("error_description", "Refund failed")
                    refund.processed_at = timezone.now() if refund.status == "processed" else None
                    refund.save(update_fields=["status", "failure_reason", "processed_at"])
                    _update_refund_totals(refund.payment)
            event.status = "processed"
            event.error = ""
            event.processed_at = timezone.now()
            event.save(update_fields=["status", "error", "processed_at"])
    except Exception as exc:
        event.status = "failed"
        event.error = str(exc)[:1000]
        event.save(update_fields=["status", "error"])
        raise
    return event


def _update_refund_totals(payment):
    processed = sum(
        (refund.amount for refund in payment.refunds.filter(status="processed")),
        Decimal("0.00"),
    )
    if processed >= payment.amount:
        payment.status = "refunded"
    elif processed > 0:
        payment.status = "partially_refunded"
    payment.save(update_fields=["status", "updated_at"])
    order = payment.order
    if order and processed >= payment.amount:
        order.payment_status = "Refunded"
        fields = ["payment_status", "updated_at"]
        if hasattr(order, "refund_amount"):
            order.refund_amount = processed
            order.refunded_at = timezone.now()
            fields.extend(["refund_amount", "refunded_at"])
        order.save(update_fields=fields)


def request_payment_refund(payment, amount, reason, order=None):
    with transaction.atomic():
        payment = PaymentTransaction.objects.select_for_update().get(pk=payment.pk)
        if payment.status not in {"captured", "partially_refunded"}:
            raise ValueError("This payment is not available for refund.")
        already = sum((item.amount for item in payment.refunds.exclude(status="failed")), Decimal("0.00"))
        amount = money(amount)
        if amount <= 0 or already + amount > payment.amount:
            raise ValueError("Refund amount exceeds the refundable payment balance.")
        linked_order = order or payment.order
        refund = RefundTransaction.objects.create(
            payment=payment,
            amount=amount,
            reason=reason[:255],
            **(order_link(linked_order) if linked_order else {}),
        )
    try:
        response = requests.post(
            f"https://api.razorpay.com/v1/payments/{payment.provider_payment_id}/refund",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            headers={"X-Refund-Idempotency": str(refund.idempotency_key)},
            json={"amount": int(amount * 100), "notes": {"reason": reason[:200]}},
            timeout=30,
        )
        response.raise_for_status()
        provider = response.json()
        refund.provider_refund_id = provider["id"]
        refund.status = "processed" if provider.get("status") == "processed" else "processing"
        refund.processed_at = timezone.now() if refund.status == "processed" else None
        refund.save(update_fields=["provider_refund_id", "status", "processed_at"])
        _update_refund_totals(payment)
    except (requests.RequestException, KeyError, ValueError) as exc:
        refund.status = "failed"
        refund.failure_reason = str(exc)[:1000]
        refund.save(update_fields=["status", "failure_reason"])
        raise
    return refund


def request_refund(order, amount, reason):
    payment = PaymentTransaction.objects.filter(
        status__in=("captured", "partially_refunded"), **order_link(order)
    ).order_by("-created_at").first()
    if not payment:
        raise ValueError("No captured online payment is available for this order.")
    return request_payment_refund(payment, amount, reason, order=order)
