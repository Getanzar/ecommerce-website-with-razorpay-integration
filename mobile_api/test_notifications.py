from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.management import call_command
from .models import Notification, NotificationPreference, PushDevice, PushReceipt, DeviceSession
from .notifications import send_customer_notification, reconcile_push_receipts
from .authentication import issue_session


class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notify")
        self.device = PushDevice.objects.create(user=self.user, expo_push_token="ExpoPushToken[test]")

    @patch("mobile_api.notifications.requests.post")
    def test_outbox_sends_once_and_persists_ticket(self, post):
        row = Notification.objects.create(user=self.user, title="Order", body="Placed")
        post.return_value.json.return_value = {"data": [{"status": "ok", "id": "ticket"}]}
        call_command("send_mobile_notifications")
        call_command("send_mobile_notifications")
        self.assertEqual(post.call_count, 1)
        row.refresh_from_db(); self.assertEqual(row.push_status, "sent")
        self.assertEqual(PushReceipt.objects.get().ticket_id, "ticket")

    @patch("mobile_api.notifications.requests.post")
    def test_disabled_preference_keeps_inbox_without_push(self, post):
        NotificationPreference.objects.create(user=self.user, order_updates=False)
        Notification.objects.create(user=self.user, title="Order", body="Placed")
        call_command("send_mobile_notifications")
        self.assertEqual(Notification.objects.count(), 1)
        post.assert_not_called()

    @patch("mobile_api.notifications.requests.post")
    def test_revoked_device_does_not_receive_push(self, post):
        issue_session(self.user)
        session = DeviceSession.objects.get(user=self.user)
        session.revoked_at = timezone.now(); session.save()
        self.device.session = session; self.device.save()
        send_customer_notification(self.user, "Title", "Body")
        post.assert_not_called()

    @patch("mobile_api.notifications.requests.post")
    def test_invalid_device_receipt_disables_registration(self, post):
        receipt = PushReceipt.objects.create(ticket_id="old-ticket", device=self.device)
        PushReceipt.objects.filter(pk=receipt.pk).update(created_at=timezone.now() - timedelta(minutes=20))
        post.return_value.json.return_value = {"data": {"old-ticket": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}}
        reconcile_push_receipts()
        self.device.refresh_from_db(); self.assertFalse(self.device.active)
