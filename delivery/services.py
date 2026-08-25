import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
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
        },
    )
    return delivery


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
    order.status = "delivered"
    update_fields = ["status", "updated_at"]
    if order.payment_method == "cod":
        order.payment_status = "Paid"
        update_fields.append("payment_status")
    order.save(update_fields=update_fields)
    DeliveryEarning.objects.get_or_create(
        delivery=delivery, defaults={"agent": agent, "amount": delivery.agent_earning}
    )
