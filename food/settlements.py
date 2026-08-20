from decimal import Decimal
from django.utils import timezone
from orders.settlements import next_morning
from .models import FoodSellerSettlement

def create_food_settlement(order):
    if order.payment_status != "Paid" or order.status == "cancelled":
        return None
    if order.payment_method == "cod" and order.status != "delivered":
        return None
    seller = order.restaurant.seller
    net = (order.subtotal / (Decimal("1") + seller.commission_percent / Decimal("100"))).quantize(Decimal("0.01"))
    return FoodSellerSettlement.objects.get_or_create(
        order=order,
        defaults={"seller": seller, "gross_amount": order.subtotal, "commission_amount": order.subtotal-net,
                  "net_amount": net, "payment_method": order.payment_method, "scheduled_for": next_morning(timezone.now())},
    )[0]
