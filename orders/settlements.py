from datetime import datetime, time, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from .models import Order, OrderItem, SellerNotification, SellerReturnDebit, SellerSettlement


def next_morning(value, hour=9):
    local_value = timezone.localtime(value)
    target_date = local_value.date() + timedelta(days=1)
    naive = datetime.combine(target_date, time(hour=hour))
    return timezone.make_aware(naive, timezone.get_current_timezone())


@transaction.atomic
def create_settlements_for_order(order):
    """Create seller ledger entries once the platform has actually received payment."""
    if order.status in {"Cancelled", "Returned"}:
        order.seller_settlements.filter(status__in=["scheduled", "failed", "on_hold"]).update(
            status="reversed", failure_reason=f"Order {order.status.lower()}."
        )
        return []
    if order.payment_status != "Paid":
        return []
    # COD cash is not platform money until delivery/collection is confirmed.
    if order.payment_method == "cod" and order.status != "Delivered":
        return []

    from payments.models import SellerDeliveryCharge
    from payments.pricing import money, percentage

    seller_ids = OrderItem.objects.filter(
        order=order, product__seller__isnull=False,
    ).exclude(fulfillment_status="cancelled").values_list("product__seller", flat=True).distinct()
    created = []
    for seller_id in seller_ids:
        from accounts.models import SellerProfile
        seller = SellerProfile.objects.get(pk=seller_id)
        items = OrderItem.objects.filter(order=order, product__seller_id=seller_id).exclude(fulfillment_status="cancelled")
        merchant = Decimal("0.00")
        merchandise_gst = Decimal("0.00")
        commission = Decimal("0.00")
        for item in items:
            legacy_base = item.price / (Decimal("1") + seller.commission_percent / Decimal("100"))
            unit_base = item.seller_unit_price or legacy_base
            merchant += unit_base * item.quantity
            merchandise_gst += item.product_tax_amount
            commission += item.platform_fee_amount
        merchant = money(merchant)
        seller_net = money(merchant + merchandise_gst)
        delivery = SellerDeliveryCharge.objects.filter(parcel_order=order, seller=seller).first()
        delivery_charge = delivery.amount_due if delivery else Decimal("0.00")
        tcs = percentage(merchant, getattr(settings, "ECOMMERCE_TCS_PERCENT", "0.50"))
        settlement_status = (
            "on_hold"
            if delivery and delivery.provider == "delhivery" and delivery.status != "reconciled"
            else "scheduled"
        )
        settlement, was_created = SellerSettlement.objects.get_or_create(
            seller=seller,
            order=order,
            defaults={
                "gross_amount": seller_net,
                "commission_amount": money(commission),
                "net_amount": seller_net,
                "delivery_charge": delivery_charge,
                "tcs_amount": tcs,
                "payment_method": order.payment_method,
                "status": settlement_status,
                "scheduled_for": next_morning(timezone.now()),
            },
        )
        if not was_created and settlement.status in {"scheduled", "failed", "on_hold"}:
            settlement.delivery_charge = delivery_charge
            settlement.tcs_amount = tcs
            settlement.status = settlement_status
            settlement.save(update_fields=["delivery_charge", "tcs_amount", "status", "updated_at"])
        if was_created:
            created.append(settlement)
    return created


def submit_razorpayx_payout(settlement):
    seller = settlement.seller
    if not seller.payouts_enabled or not seller.razorpay_fund_account_id:
        raise ValueError("Seller payout account is not verified or enabled.")
    account_number = getattr(settings, "RAZORPAYX_ACCOUNT_NUMBER", "")
    key_id = getattr(settings, "RAZORPAYX_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAYX_KEY_SECRET", "")
    if not all([account_number, key_id, key_secret]):
        raise ValueError("RazorpayX payout credentials are not configured.")

    response = requests.post(
        "https://api.razorpay.com/v1/payouts",
        auth=(key_id, key_secret),
        json={
            "account_number": account_number,
            "fund_account_id": seller.razorpay_fund_account_id,
            "amount": int(settlement.payout_amount * 100),
            "currency": "INR",
            "mode": getattr(settings, "SELLER_PAYOUT_MODE", "IMPS"),
            "purpose": "payout",
            "queue_if_low_balance": True,
            "reference_id": f"settlement-{settlement.payout_reference_key}",
            "narration": "ZIYAMART seller payout",
            "notes": {"order_id": str(settlement.order_id), "seller_id": str(settlement.seller_id)},
        },
        headers={"X-Payout-Idempotency": f"ziyamart-settlement-{settlement.payout_reference_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_razorpayx_payout(payout_id):
    key_id = getattr(settings, "RAZORPAYX_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAYX_KEY_SECRET", "")
    response = requests.get(
        f"https://api.razorpay.com/v1/payouts/{payout_id}",
        auth=(key_id, key_secret), timeout=30,
    )
    response.raise_for_status()
    return response.json()


@transaction.atomic
def create_return_debit(return_request):
    item = return_request.order_item
    if not item or not item.product.seller_id or return_request.refund_status != "Processed":
        return None
    seller = item.product.seller
    amount = (item.total / (Decimal("1") + seller.commission_percent / Decimal("100"))).quantize(Decimal("0.01"))
    debit, _ = SellerReturnDebit.objects.get_or_create(
        return_request=return_request,
        defaults={"seller": seller, "original_amount": amount, "remaining_amount": amount},
    )
    available = SellerSettlement.objects.filter(
        seller=seller, status__in=["scheduled", "failed"]
    ).aggregate(total=Sum(F("net_amount") - F("deductions_amount") - F("delivery_charge") - F("tcs_amount")))["total"] or Decimal("0")
    shortfall = max(debit.remaining_amount - available, Decimal("0"))
    if shortfall:
        SellerNotification.objects.update_or_create(
            seller=seller, kind="return_balance_due", is_read=False,
            defaults={
                "title": "Add funds for a customer return",
                "message": f"Your upcoming payouts are insufficient. Please add ₹{shortfall} through marketplace support to complete the return recovery.",
            },
        )
    return debit


@transaction.atomic
def apply_return_debits(settlement):
    available = settlement.payout_amount
    debits = SellerReturnDebit.objects.select_for_update().filter(
        seller=settlement.seller, remaining_amount__gt=0
    ).order_by("created_at")
    for debit in debits:
        applied = min(available, debit.remaining_amount)
        if applied <= 0:
            break
        settlement.deductions_amount += applied
        debit.remaining_amount -= applied
        available -= applied
        debit.save(update_fields=["remaining_amount"])
    settlement.save(update_fields=["deductions_amount", "updated_at"])
    outstanding = debits.aggregate(total=Sum("remaining_amount"))["total"] or Decimal("0")
    if outstanding > 0:
        SellerNotification.objects.update_or_create(
            seller=settlement.seller, kind="return_balance_due", is_read=False,
            defaults={
                "title": "Return balance needs payment",
                "message": f"₹{outstanding} remains due for customer returns. Future payouts will be adjusted; please add funds through marketplace support.",
            },
        )
    return settlement.payout_amount
