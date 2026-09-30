from django.core.management.base import BaseCommand
from django.db import transaction
from mobile_api.models import Notification, NotificationPreference, PushDevice
from mobile_api.notifications import send_customer_notification, reconcile_push_receipts


class Command(BaseCommand):
    help = "Drain the mobile push outbox; run every minute. Inbox entries remain available."

    def handle(self, **options):
        reconcile_push_receipts()
        ids = list(Notification.objects.filter(push_status="pending", attempts__lt=5).values_list("id", flat=True)[:100])
        for pk in ids:
            with transaction.atomic():
                row = Notification.objects.select_for_update().get(pk=pk)
                if row.push_status != "pending":
                    continue
                preferences, _ = NotificationPreference.objects.get_or_create(user=row.user)
                if not getattr(preferences, row.category, False) or not PushDevice.objects.filter(user=row.user, active=True).exists():
                    row.push_status = "skipped"
                else:
                    tickets = send_customer_notification(row.user, row.title, row.body, {**row.data, "notification_id": row.pk}, row.category)
                    row.attempts += 1
                    if tickets and all(ticket.get("status") == "ok" for ticket in tickets):
                        row.push_status = "sent"
                    elif row.attempts >= 5:
                        row.push_status = "failed"
                row.save(update_fields=["push_status", "attempts"])
