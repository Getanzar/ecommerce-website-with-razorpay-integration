import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import DeliveryEarning, LocalDelivery


def ensure_grocery_delivery(order):
    """Create an agent job only for local grocery orders; parcel orders are rejected."""
    if order.delivery_mode != "local":
        return None
    if None in (order.store.latitude, order.store.longitude, order.latitude, order.longitude):
        return None
    if order.store.pincode != order.pincode:
        return None
    area = order.store.service_areas.filter(
        pincode=order.pincode, is_active=True, delivery_mode="local"
    ).first()
    if not area:
        return None
    delivery, _ = LocalDelivery.objects.get_or_create(
        grocery_order=order,
        defaults={
            "pincode": order.pincode,
            "pickup_name": order.store.name,
            "pickup_address": order.store.address,
            "pickup_latitude": order.store.latitude,
            "pickup_longitude": order.store.longitude,
            "customer_name": order.full_name,
            "customer_phone": order.phone,
            "delivery_address": f"{order.address}, {order.city}, {order.state} - {order.pincode}",
            "customer_latitude": order.latitude,
            "customer_longitude": order.longitude,
            "delivery_fee": order.delivery_fee,
            "agent_earning": order.delivery_fee,
            "collection_amount": order.total if order.payment_method == "cod" else Decimal("0.00"),
        },
    )
    return delivery


def ensure_food_delivery(order):
    if None in (order.restaurant.latitude, order.restaurant.longitude, order.latitude, order.longitude):
        return None
    if order.restaurant.pincode != order.pincode or not order.restaurant.service_areas.filter(pincode=order.pincode, is_active=True).exists():
        return None
    delivery, _ = LocalDelivery.objects.get_or_create(
        food_order=order,
        defaults={
            "pincode": order.pincode,
            "pickup_name": order.restaurant.name,
            "pickup_address": order.restaurant.seller.business_address or order.restaurant.name,
            "pickup_latitude": order.restaurant.latitude,
            "pickup_longitude": order.restaurant.longitude,
            "customer_name": order.full_name,
            "customer_phone": order.phone,
            "delivery_address": f"{order.address}, {order.city}, {order.state} - {order.pincode}",
            "customer_latitude": order.latitude,
            "customer_longitude": order.longitude,
            "delivery_fee": order.delivery_fee,
            "agent_earning": order.delivery_fee,
            "collection_amount": order.total if order.payment_method == "cod" else Decimal("0.00"),
        },
    )
    return delivery


def ensure_parcel_deliveries(order, delivery_charges):
    deliveries = []
    for charge in delivery_charges:
        if charge.provider != "local":
            continue
        seller = charge.seller
        if (
            seller.business_pincode != order.pincode
            or None in (seller.business_latitude, seller.business_longitude, order.latitude, order.longitude)
        ):
            continue
        delivery, _ = LocalDelivery.objects.get_or_create(
            parcel_order=order,
            parcel_seller=seller,
            defaults={
                "pincode": order.pincode,
                "pickup_name": seller.store_name,
                "pickup_address": seller.business_address,
                "pickup_latitude": seller.business_latitude,
                "pickup_longitude": seller.business_longitude,
                "customer_name": order.full_name,
                "customer_phone": order.phone,
                "delivery_address": f"{order.address}, {order.city}, {order.state} - {order.pincode}",
                "customer_latitude": order.latitude,
                "customer_longitude": order.longitude,
                "delivery_fee": charge.quoted_total,
                "agent_earning": charge.quoted_total,
                "collection_amount": charge.customer_collection_amount if order.payment_method == "cod" else Decimal("0.00"),
            },
        )
        deliveries.append(delivery)
    return deliveries


def issue_delivery_otp(delivery):
    otp = f"{secrets.randbelow(900000) + 100000}"
    delivery.delivery_otp_hash = make_password(otp)
    delivery.otp_expires_at = timezone.now() + timedelta(hours=6)
    delivery.save(update_fields=["delivery_otp_hash", "otp_expires_at", "updated_at"])
    email = delivery.source_order.user.email
    if email:
        send_mail(
            f"Delivery OTP for order #{delivery.source_order.pk}",
            f"Your ZIYAMART delivery OTP is {otp}. Share it only after receiving your order.",
            None, [email], fail_silently=True,
        )
    return otp


def otp_is_valid(delivery, otp):
    return bool(
        delivery.delivery_otp_hash
        and delivery.otp_expires_at
        and delivery.otp_expires_at >= timezone.now()
        and check_password(otp, delivery.delivery_otp_hash)
    )


@transaction.atomic
def complete_delivery(delivery, agent):
    delivery.status = "delivered"
    delivery.delivered_at = timezone.now()
    # Do not retain a rider/customer's precise location after fulfillment.
    delivery.agent_latitude = None
    delivery.agent_longitude = None
    delivery.location_accuracy_meters = None
    delivery.location_updated_at = None
    delivery.save(update_fields=[
        "status", "delivered_at", "agent_latitude", "agent_longitude",
        "location_accuracy_meters", "location_updated_at", "updated_at",
    ])
    order = delivery.source_order
    if delivery.parcel_order_id:
        other_active = order.local_deliveries.exclude(pk=delivery.pk).exclude(status="delivered").exists()
        if not other_active and not order.sellerdeliverycharges.filter(provider="delhivery").exclude(carrier_status="delivered").exists():
            order.status = "Delivered"
    else:
        order.status = "delivered"
    update_fields = ["status", "updated_at"]
    if delivery.parcel_order_id and order.status == "Delivered" and not order.delivered_at:
        order.delivered_at = timezone.now()
        update_fields.append("delivered_at")
    order.save(update_fields=update_fields)
    platform_percent = Decimal(str(getattr(settings, "DELIVERY_AGENT_PLATFORM_FEE_PERCENT", "10.00")))
    platform_fee = (delivery.agent_earning * platform_percent / Decimal("100")).quantize(Decimal("0.01"))
    earning_status = "pending" if order.payment_method == "cod" else "payable"
    earning, _ = DeliveryEarning.objects.get_or_create(
        delivery=delivery,
        defaults={
            "agent": agent,
            "amount": delivery.agent_earning,
            "platform_fee_percent": platform_percent,
            "platform_fee_amount": platform_fee,
            "net_amount": delivery.agent_earning - platform_fee,
            "status": earning_status,
            "scheduled_for": timezone.now() + timedelta(hours=12),
        },
    )
    if order.payment_method == "cod":
        from payments.models import CODRemittance
        from payments.services import order_link
        CODRemittance.objects.get_or_create(
            delivery=delivery,
            defaults={
                "agent": agent,
                "seller": delivery.parcel_seller if delivery.parcel_order_id else None,
                "source": "local_agent",
                "amount": delivery.collection_amount or getattr(order, "total_price", getattr(order, "total", 0)),
                "status": "collected",
                "collected_at": timezone.now(),
                **order_link(order),
            },
        )
    if order.payment_status == "Paid":
        if delivery.food_order_id:
            from food.settlements import create_food_settlement
            create_food_settlement(order)
        elif delivery.grocery_order_id:
            from groceries.settlements import create_grocery_settlement
            create_grocery_settlement(order)
        elif delivery.parcel_order_id:
            from orders.settlements import create_settlements_for_order
            create_settlements_for_order(order)
    return earning
