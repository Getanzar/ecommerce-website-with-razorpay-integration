"""Delivery data shared by mobile quote and order creation."""
from django.utils import timezone
from rest_framework import serializers


class DeliveryLocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    gps_accuracy_meters = serializers.IntegerField(min_value=0, max_value=500)
    gps_captured_at = serializers.DateTimeField()

    def validate_gps_captured_at(self, value):
        if abs((timezone.now() - value).total_seconds()) > 300:
            raise serializers.ValidationError("Capture your delivery location again; this location has expired.")
        return value


def order_location(quote):
    location = quote.get("location") or {}
    return {key: location[key] for key in ("latitude", "longitude", "gps_accuracy_meters") if key in location}


def save_delivery_records(order, quote):
    from payments.services import create_local_seller_delivery_charge, create_seller_delivery_charges
    if hasattr(order, "restaurant"):
        store = order.restaurant
    elif hasattr(order, "store"):
        store = order.store
    else:
        from orders.commerce import _quotes_from_snapshot
        create_seller_delivery_charges(order, _quotes_from_snapshot({"quotes": quote.get("delivery_quotes", [])}))
        return
    create_local_seller_delivery_charge(order, store.seller, store.pincode, order.pincode, store.delivery_fee)


def dispatch_local_parcel(order):
    """Dispatch persisted local and courier packages after the order commits."""
    if order.payment_method != "cod" and order.payment_status != "Paid":
        return
    if order.status in {"Cancelled", "Returned"}:
        return
    from django.db import transaction
    from delivery.services import ensure_parcel_deliveries
    ensure_parcel_deliveries(order, order.sellerdeliverycharges.filter(provider="local").select_related("seller"))
    transaction.on_commit(lambda: _dispatch_courier(order.pk))


def _dispatch_courier(order_id):
    from orders.models import Order
    from orders.shipping import manifest_delhivery_shipments
    order = Order.objects.get(pk=order_id)
    manifest_delhivery_shipments(order, order.sellerdeliverycharges.filter(provider="delhivery").select_related("seller"))
