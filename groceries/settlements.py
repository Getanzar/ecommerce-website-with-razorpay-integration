from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from orders.settlements import next_morning
from payments.models import SellerDeliveryCharge
from payments.pricing import percentage

from .models import GrocerySellerSettlement


def create_grocery_settlement(order):
    if order.payment_status != "Paid" or order.status == "cancelled":
        return None
    if order.payment_method == "cod" and order.status != "delivered":
        return None
    seller = order.store.seller
    breakdown = order.chargebreakdowns.first()
    merchant = breakdown.merchant_subtotal if breakdown else order.subtotal
    merchandise_gst = breakdown.merchandise_gst if breakdown else Decimal("0.00")
    commission = breakdown.platform_fee if breakdown else Decimal("0.00")
    delivery = SellerDeliveryCharge.objects.filter(grocery_order=order, seller=seller).first()
    settlement, created = GrocerySellerSettlement.objects.get_or_create(
        order=order,
        defaults={
            "seller": seller,
            "gross_amount": merchant + merchandise_gst,
            "commission_amount": commission,
            "net_amount": merchant + merchandise_gst,
            "delivery_charge": delivery.amount_due if delivery else order.delivery_fee,
            "tcs_amount": percentage(merchant, getattr(settings, "ECOMMERCE_TCS_PERCENT", "0.50")),
            "payment_method": order.payment_method,
            "scheduled_for": next_morning(timezone.now()),
        },
    )
    if not created and settlement.status in {"scheduled", "failed"}:
        settlement.delivery_charge = delivery.amount_due if delivery else order.delivery_fee
        settlement.save(update_fields=["delivery_charge", "updated_at"])
    return settlement
