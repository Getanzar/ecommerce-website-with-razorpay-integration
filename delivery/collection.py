"""Per-delivery collection; provider capture and cash custody are separate."""
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from payments.models import CODRemittance, PaymentTransaction
from payments.services import order_link
from .models import DeliveryCollection, LocalDelivery


class CollectionError(ValueError):
    pass


class ProviderRejected(CollectionError):
    pass


def provider(method, path, payload=None):
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise CollectionError("Online collection is not configured. Choose cash or contact support.")
    try:
        response = requests.request(method, "https://api.razorpay.com/v1" + path,
                                    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
                                    json=payload, timeout=15)
        if 400 <= response.status_code < 500:
            raise ProviderRejected("Razorpay rejected this request. Check that UPI QR collection is enabled for ZIYAMART or choose cash.")
        response.raise_for_status()
        return response.json()
    except ProviderRejected:
        raise
    except (requests.RequestException, ValueError) as exc:
        raise CollectionError("Payment service unavailable. Refresh payment status before collecting again.") from exc


def collection_data(delivery):
    record = DeliveryCollection.objects.filter(delivery=delivery).first()
    cash = CODRemittance.objects.filter(delivery=delivery, status__in=["collected", "remitted", "settled"]).first()
    if not record and cash:
        return {"paid": True, "method": "cash", "amount": str(cash.amount), "amount_due": "0.00", "qr_image_url": "", "status": "paid"}
    paid = bool(record and record.status == "paid") or (not record and delivery.source_order.payment_status == "Paid")
    return {"paid": paid, "method": record.method if record else ("online" if paid else ""),
            "amount": str(delivery.collection_amount), "amount_due": "0.00" if paid else str(delivery.collection_amount),
            "qr_image_url": record.qr_image_url if record and not paid else "",
            "status": record.status if record else ("paid" if paid else "pending")}


def _validate(delivery):
    if delivery.status != "out_for_delivery" or delivery.source_order.status.lower() in {"cancelled", "returned", "delivered"}:
        raise CollectionError("Payment collection is only available on an active out-for-delivery order.")
    if delivery.source_order.payment_method != "cod":
        raise CollectionError("This order was paid online. Do not collect again.")
    if delivery.collection_amount <= 0:
        raise CollectionError("The collection amount needs review. Contact support.")


def _mark_paid(record, method, entity=None):
    delivery = record.delivery
    order = type(delivery.source_order).objects.select_for_update().get(pk=delivery.source_order.pk)
    if order.status.lower() in {"cancelled", "returned", "delivered"}:
        raise CollectionError("This order is closed. Contact support to reconcile its payment.")
    if record.status == "paid":
        return
    if method == "cash":
        CODRemittance.objects.get_or_create(delivery=delivery, defaults={
            "agent": delivery.agent, "seller": delivery.parcel_seller if delivery.parcel_order_id else None,
            "source": "local_agent", "amount": record.amount, "status": "collected",
            "collected_at": timezone.now(), **order_link(order),
        })
    else:
        payment, _ = PaymentTransaction.objects.get_or_create(provider_payment_id=entity["id"], defaults={
            "user": order.user, "channel_name": "parcel" if delivery.parcel_order_id else "food" if delivery.food_order_id else "grocery",
            "provider": "razorpay", "amount": record.amount, "currency": "INR", "status": "captured",
            "captured_at": timezone.now(), "snapshot": {"delivery_id": delivery.pk, "qr_id": record.qr_id},
            **order_link(order),
        })
        if payment.snapshot.get("delivery_id") != delivery.pk or payment.amount != record.amount:
            raise CollectionError("This payment belongs to another delivery. Contact support.")
        record.payment = payment
    record.method, record.status, record.paid_at = method, "paid", timezone.now()
    record.save(update_fields=["method", "status", "paid_at", "payment", "updated_at"])
    # A parcel order can include other local agents and carrier shipments.
    required = getattr(order, "total_price", getattr(order, "total", Decimal("0")))
    if customer_paid_amount(order) >= required:
        order.payment_status = "Paid"
        order.save(update_fields=["payment_status", "updated_at"])


def customer_paid_amount(order):
    total = DeliveryCollection.objects.filter(**{"delivery__" + next(iter(order_link(order))): order}, status="paid").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    legacy_cash = CODRemittance.objects.filter(**order_link(order), status__in=["collected", "remitted", "settled"]).exclude(delivery__collection__status="paid").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return total + legacy_cash


def _check_qr(record):
    if not record.qr_id:
        return False
    data = provider("GET", f"/payments/qr_codes/{record.qr_id}/payments?count=100")
    for entity in data.get("items", []):
        if entity.get("status") == "captured":
            if entity.get("amount") != int(record.amount * 100) or entity.get("currency") != "INR":
                raise CollectionError("Payment amount does not match this delivery. Contact support.")
            _mark_paid(record, "online", entity)
            return True
        if entity.get("status") == "authorized":
            raise CollectionError("An online payment is processing. Check again before collecting cash.")
    return False


def collect_payment(delivery_id, agent, action):
    if action not in {"cash", "online", "check"}:
        raise CollectionError("Unknown payment action.")
    # Commit the issuing marker even if the provider times out; a retry cannot
    # create a second payable QR after an uncertain response.
    create_qr = False
    with transaction.atomic():
        delivery = LocalDelivery.objects.select_for_update().get(pk=delivery_id, agent=agent)
        _validate(delivery)
        record = DeliveryCollection.objects.select_for_update().filter(delivery=delivery).first()
        if not record and delivery.source_order.payment_status == "Paid":
            return collection_data(delivery)
        if not record:
            record = DeliveryCollection.objects.create(delivery=delivery, amount=delivery.collection_amount)
        if record.status == "paid":
            return collection_data(delivery)
        if record.status == "issuing":
            raise CollectionError("QR creation needs reconciliation. Contact support before collecting another payment.")
        if record.qr_id and _check_qr(record):
            return collection_data(delivery)
        if action == "cash":
            if record.qr_id:
                qr = provider("GET", f"/payments/qr_codes/{record.qr_id}")
                if qr.get("status") != "closed":
                    provider("POST", f"/payments/qr_codes/{record.qr_id}/close", {})
                if _check_qr(record):
                    return collection_data(delivery)
                qr = provider("GET", f"/payments/qr_codes/{record.qr_id}")
                if qr.get("status") != "closed" or qr.get("payments_count_received", 0):
                    raise CollectionError("The QR has a payment in progress. Check its payment status first.")
            _mark_paid(record, "cash")
        elif action == "online" and not record.qr_id:
            if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
                raise CollectionError("Online collection is not configured. Choose cash or contact support.")
            record.method, record.status = "online", "issuing"
            record.save(update_fields=["method", "status", "updated_at"])
            create_qr = True
    if create_qr:
        try:
            qr = provider("POST", "/payments/qr_codes", {
                "type": "upi_qr", "name": "ZIYAMART", "usage": "single_use", "fixed_amount": True,
                "payment_amount": int(record.amount * 100), "description": f"ZIYAMART delivery #{delivery.pk}",
                "notes": {"delivery_id": str(delivery.pk)},
            })
        except ProviderRejected:
            DeliveryCollection.objects.filter(pk=record.pk, status="issuing").update(status="pending", method="")
            raise
        if not qr.get("id") or not str(qr.get("image_url", "")).startswith("https://") or qr.get("payment_amount") != int(record.amount * 100):
            raise CollectionError("QR creation needs reconciliation. Contact support.")
        with transaction.atomic():
            record = DeliveryCollection.objects.select_for_update().get(pk=record.pk)
            record.qr_id, record.qr_image_url, record.status = qr["id"], qr["image_url"], "pending"
            record.save(update_fields=["qr_id", "qr_image_url", "status", "updated_at"])
    return collection_data(delivery)


def reconcile_qr(qr_id):
    with transaction.atomic():
        record = DeliveryCollection.objects.select_for_update().filter(qr_id=qr_id).first()
        if not record or record.status == "paid":
            return
        _validate(record.delivery)
        _check_qr(record)
