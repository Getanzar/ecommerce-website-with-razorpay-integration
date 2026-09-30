"""Audited operations execution. Persist refund intent before contacting Razorpay."""
from decimal import Decimal
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from payments.models import PaymentTransaction, RefundTransaction
from payments.services import order_link, _update_refund_totals
from .models import SellerCase, Notification
from .partners import seller_orders


def prepare_case(case_id):
    with transaction.atomic():
        case = SellerCase.objects.select_for_update().get(pk=case_id)
        if case.executed_at:
            return case
        if case.status not in {"open", "reviewing"} or case.kind == "dispute":
            raise ValidationError("Only open cancellation or refund requests can be executed.")
        target = seller_orders(case.seller, case.order_kind).select_for_update().filter(pk=case.order_item_id if case.order_kind == "shop" else case.order_id).first()
        if not target:
            raise ValidationError("This seller no longer owns the requested order item.")
        order = target.order if case.order_kind == "shop" else target
        order = type(order).objects.select_for_update().get(pk=order.pk)
        from orders.models import SellerSettlement
        from food.models import FoodSellerSettlement
        from groceries.models import GrocerySellerSettlement
        settlement_model = {"shop": SellerSettlement, "food": FoodSellerSettlement, "grocery": GrocerySellerSettlement}[case.order_kind]
        settlement = settlement_model.objects.select_for_update().filter(seller=case.seller, order=order).first()
        if settlement and (settlement.status in {"paid", "processing"} or settlement.provider_payout_id):
            raise ValidationError("Payout already started. Reconcile seller recovery in the finance workspace first.")
        # A completed delivery/return requires the existing return and debit ledger.
        status = target.fulfillment_status if case.order_kind == "shop" else order.status
        if case.kind == "cancellation" and order.status.lower() in {"cancelled", "returned", "delivered"}:
            raise ValidationError("This order is already closed. Use the returns or finance workspace.")
        if case.kind == "cancellation" and order.payment_method == "cod" and order.payment_status == "Paid":
            raise ValidationError("Cash has already been collected. Reconcile repayment in the finance workspace first.")
        allowed = {"shop": {"new", "accepted", "packed"}, "food": {"placed", "accepted"}, "grocery": {"placed", "accepted", "packing"}}
        if case.kind == "cancellation" and status not in allowed[case.order_kind]:
            raise ValidationError("Fulfilment already progressed. Use a supervised return workflow.")
        if case.kind == "refund" and status != "cancelled":
            raise ValidationError("Refund-only execution requires a cancelled item/order. Delivered items use the Returns workspace.")
        amount = target.total if case.order_kind == "shop" else order.total
        if SellerCase.objects.filter(seller=case.seller, order_kind=case.order_kind, order_id=case.order_id,
                                     order_item_id=case.order_item_id, refund__isnull=False).exclude(pk=case.pk).exists():
            raise ValidationError("This item already has a reserved refund. Reconcile that case instead.")
        payment = None
        if order.payment_method == "online":
            payment = PaymentTransaction.objects.select_for_update().filter(**order_link(order), status__in=["captured", "partially_refunded"]).first()
            if not payment:
                raise ValidationError("Reconcile the online payment before executing cancellation or refund.")
            reserved = sum((r.amount for r in payment.refunds.exclude(status="failed")), Decimal("0"))
            if amount <= 0 or reserved + amount > payment.amount:
                raise ValidationError("Refund exceeds the remaining payment balance.")
        elif case.kind == "refund":
            raise ValidationError("COD refunds require an independently reconciled repayment in the finance workspace.")
        if case.kind == "cancellation":
            from delivery.models import LocalDelivery
            deliveries = LocalDelivery.objects.select_for_update().filter(**order_link(order))
            if case.order_kind == "shop":
                deliveries = deliveries.filter(parcel_seller=case.seller)
            if deliveries.filter(status__in=["picked_up", "out_for_delivery", "delivered"]).exists():
                raise ValidationError("Dispatch has already picked up this order. Arrange a supervised return.")
            if case.order_kind == "shop":
                target.fulfillment_status = "cancelled"
                target.save(update_fields=["fulfillment_status"])
                if target.variant_id:
                    type(target.variant).objects.filter(pk=target.variant_id).update(stock=F("stock") + target.quantity)
                if not order.items.exclude(fulfillment_status="cancelled").exists():
                    order.status = "Cancelled"
                    order.cancelled_at = timezone.now()
                    order.cancel_reason = case.reason[:500]
                    order.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
            else:
                order.status = "cancelled"
                order.save(update_fields=["status", "updated_at"])
                if case.order_kind == "grocery":
                    for item in order.items.select_related("product"):
                        type(item.product).objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
            if case.order_kind == "shop" and order.items.filter(product__seller=case.seller).exclude(fulfillment_status="cancelled").exists():
                deliveries = deliveries.none()
            for delivery in deliveries:
                delivery.status = "cancelled"
                delivery.save(update_fields=["status", "updated_at"])
            if settlement:
                deduction = target.seller_total if case.order_kind == "shop" else settlement.net_amount
                settlement.deductions_amount = min(settlement.net_amount, settlement.deductions_amount + deduction)
                if settlement.payout_amount <= 0:
                    settlement.status = "offset"
                settlement.save(update_fields=["deductions_amount", "status", "updated_at"])
        if payment:
            case.refund = RefundTransaction.objects.create(payment=payment, amount=amount, reason=f"Seller case #{case.pk}: {case.reason}"[:255], **order_link(order))
        case.executed_at = timezone.now()
        case.status = "reviewing" if payment else "resolved"
        case.resolution = "Cancellation executed; refund awaiting provider confirmation." if payment else "Cancellation executed. No online refund required."
        case.save()
        Notification.objects.create(user=order.user, title="Order request processed", body=case.resolution, data={"kind": case.order_kind, "order_id": order.pk})
        return case


def submit_case_refund(case):
    """An uncertain request remains reserved. Retries reuse its provider idempotency key."""
    if not case.refund_id:
        return
    refund = case.refund
    if refund.status in {"processing", "processed"}:
        return
    try:
        response = requests.post(f"https://api.razorpay.com/v1/payments/{refund.payment.provider_payment_id}/refund",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            headers={"X-Refund-Idempotency": str(refund.idempotency_key)},
            json={"amount": int(refund.amount * 100), "notes": {"seller_case": str(case.pk)}}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("id") or payload.get("amount") != int(refund.amount * 100):
            raise ValueError("Provider refund response needs reconciliation.")
        with transaction.atomic():
            refund = RefundTransaction.objects.select_for_update().get(pk=refund.pk)
            refund.provider_refund_id = payload["id"]
            refund.status = "processed" if payload.get("status") == "processed" else "processing"
            refund.processed_at = timezone.now() if refund.status == "processed" else None
            refund.failure_reason = ""
            refund.save()
            _update_refund_totals(refund.payment)
    except (requests.RequestException, ValueError) as exc:
        RefundTransaction.objects.filter(pk=refund.pk).update(failure_reason="Provider outcome uncertain. Reconcile or retry this same case; do not create a new refund.")
        raise ValidationError("Refund confirmation unavailable. The reserved refund will reuse the same idempotency key on retry.") from exc
