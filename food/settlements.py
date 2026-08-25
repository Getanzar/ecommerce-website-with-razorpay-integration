from decimal import Decimal
from django.utils import timezone
from orders.settlements import next_morning
from .models import FoodSellerSettlement

def create_food_settlement(order):
    if order.payment_status != "Paid" or order.status == "cancelled":
        return None
    if order.payment_method == "cod" and order.status != "delivered":
        return None
    from payments.models import SellerDeliveryCharge
    from payments.pricing import money

    seller = order.restaurant.seller
    breakdown = order.chargebreakdowns.first()
    merchant = breakdown.merchant_subtotal if breakdown else (
        order.subtotal / (Decimal("1") + seller.commission_percent / Decimal("100"))
    ).quantize(Decimal("0.01"))
    commission = breakdown.platform_fee if breakdown else order.subtotal - merchant
    delivery = SellerDeliveryCharge.objects.filter(food_order=order, seller=seller).first()
    settlement, created = FoodSellerSettlement.objects.get_or_create(
        order=order,
        defaults={"seller": seller, "gross_amount": merchant, "commission_amount": commission,
                  "net_amount": merchant, "delivery_charge": delivery.amount_due if delivery else order.delivery_fee,
                  "tcs_amount": Decimal("0.00"), "payment_method": order.payment_method,
                  "scheduled_for": next_morning(timezone.now())},
    )
    if not created and settlement.status in {"scheduled", "failed"}:
        settlement.delivery_charge = delivery.amount_due if delivery else money(order.delivery_fee)
        settlement.save(update_fields=["delivery_charge", "updated_at"])
    return settlement
