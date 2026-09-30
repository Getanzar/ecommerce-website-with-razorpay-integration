import logging

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import NotificationPreference, PushDevice, PushReceipt

logger = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


@transaction.atomic
def notify_sellers_of_order(order):
    """Persist one actionable order alert per seller, across checkout channels."""
    from .models import Notification
    order = type(order).objects.select_for_update().get(pk=order.pk)
    if order.payment_method != "cod" and order.payment_status != "Paid":
        return
    if order.status.lower() in {"cancelled", "returned"}:
        return
    if hasattr(order, "restaurant"):
        kind, users = "food", {order.restaurant.seller.user_id}
    elif hasattr(order, "store"):
        kind, users = "grocery", {order.store.seller.user_id}
    else:
        kind, users = "shop", set(order.items.values_list("product__seller__user_id", flat=True))
    for user_id in users - {None}:
        Notification.objects.get_or_create(
            user_id=user_id, title="New seller order",
            data={"target": "seller", "kind": kind, "order_id": order.pk},
            defaults={"body": f"Order #{order.pk} received. Payment: {order.payment_status}."},
        )


def expo_headers():
    token = getattr(settings, "EXPO_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def send_customer_notification(user, title, body, data=None, category="order_updates"):
    preferences, _ = NotificationPreference.objects.get_or_create(user=user)
    if not getattr(preferences, category, False):
        return []
    devices = list(PushDevice.objects.filter(user=user, active=True).filter(Q(session__isnull=True) | Q(session__revoked_at__isnull=True, session__expires_at__gt=timezone.now())))
    messages = [{"to": d.expo_push_token, "title": title, "body": body, "data": data or {}, "sound": "default", "channelId": "orders"} for d in devices]
    if not messages:
        return []
    try:
        tickets = []
        for start in range(0, len(messages), 100):
            response = requests.post(EXPO_PUSH_URL, json=messages[start:start + 100], headers=expo_headers(), timeout=10)
            response.raise_for_status()
            batch = response.json().get("data", [])
            if not isinstance(batch, list) or len(batch) != len(messages[start:start + 100]):
                raise ValueError("Unexpected push ticket response")
            for device, ticket in zip(devices[start:start + 100], batch):
                if ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                    device.active = False
                    device.save(update_fields=["active", "updated_at"])
                if ticket.get("status") == "ok" and ticket.get("id"):
                    PushReceipt.objects.get_or_create(ticket_id=ticket["id"], defaults={"device": device})
            tickets.extend(batch)
        return tickets
    except (requests.RequestException, ValueError):
        logger.exception("Expo notification delivery failed for user %s", user.pk)
        return []


def reconcile_push_receipts():
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(minutes=15)
    rows = list(PushReceipt.objects.filter(status="pending", created_at__lt=cutoff)[:1000])
    if not rows:
        return
    try:
        response = requests.post("https://exp.host/--/api/v2/push/getReceipts", json={"ids": [row.ticket_id for row in rows]}, headers=expo_headers(), timeout=15)
        response.raise_for_status()
        data = response.json().get("data", {})
        for row in rows:
            receipt = data.get(row.ticket_id)
            if not receipt:
                if row.created_at < timezone.now() - timedelta(hours=24):
                    row.status = "unknown"
                    row.save(update_fields=["status"])
                continue
            row.status = "ok" if receipt.get("status") == "ok" else "error"
            row.error = str(receipt.get("details", {}).get("error", ""))[:100]
            row.save(update_fields=["status", "error"])
            if row.error == "DeviceNotRegistered":
                PushDevice.objects.filter(pk=row.device_id).update(active=False)
    except (requests.RequestException, ValueError):
        logger.exception("Expo push receipt reconciliation failed")
