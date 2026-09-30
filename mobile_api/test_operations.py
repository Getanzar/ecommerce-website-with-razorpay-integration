import hashlib
import hmac
from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from orders.models import Order
from payments.services import create_payment_transaction
from .authentication import issue_session
from .models import DeviceSession, Notification


class DeviceSessionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("device-user", password="very-long-password")
        self.first = issue_session(self.user, "First phone")
        self.second = issue_session(self.user, "Second phone")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.first}")

    def test_revoke_only_selected_session(self):
        rows = self.client.get("/api/v1/account/sessions/").data
        second = next(row for row in rows if not row["current"])
        self.assertEqual(self.client.delete(f'/api/v1/account/sessions/{second["id"]}/').status_code, 204)
        self.assertEqual(self.client.get("/api/v1/account/sessions/").status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.second}")
        self.assertEqual(self.client.get("/api/v1/account/sessions/").status_code, 401)

    def test_other_user_session_not_revocable(self):
        other = User.objects.create_user("other-device")
        issue_session(other)
        row = DeviceSession.objects.get(user=other)
        self.assertEqual(self.client.delete(f"/api/v1/account/sessions/{row.pk}/").status_code, 404)

    def test_expired_session_rejected(self):
        DeviceSession.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get("/api/v1/account/sessions/").status_code, 401)

    def test_notification_inbox_ownership(self):
        other = User.objects.create_user("other-inbox")
        row = Notification.objects.create(user=other, title="Private", body="Private")
        self.assertEqual(self.client.get("/api/v1/notifications/").data, [])
        self.assertEqual(self.client.patch(f"/api/v1/notifications/{row.pk}/").status_code, 404)


@override_settings(RAZORPAY_KEY_ID="test", RAZORPAY_KEY_SECRET="secret")
class NativePaymentTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user("pay-user")
        self.client.force_authenticate(self.user)
        self.order = Order.objects.create(user=self.user, full_name="Buyer", phone="9999999999", address="A", city="B", state="C", pincode="123456", total_price="100.00", payment_method="online", payment_status="Pending")
        self.payment = create_payment_transaction(self.order, "order_test")
        self.path = f"/api/v1/orders/shop/{self.order.pk}/payment/"
        self.signature = hmac.new(b"secret", b"order_test|pay_test", hashlib.sha256).hexdigest()

    def payload(self):
        return {"razorpay_order_id": "order_test", "razorpay_payment_id": "pay_test", "razorpay_signature": self.signature}

    def entity(self, **kwargs):
        return {"id": "pay_test", "order_id": "order_test", "amount": 10000, "currency": "INR", "status": "captured", **kwargs}

    @patch("mobile_api.payment_api.razorpay.Client")
    def test_signature_and_capture_are_required(self, client):
        client.return_value.payment.fetch.return_value = self.entity(status="authorized")
        response = self.client.post(self.path, self.payload(), format="json")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "Pending")

    @patch("mobile_api.payment_api.razorpay.Client")
    def test_verification_and_duplicate_are_idempotent(self, client):
        client.return_value.payment.fetch.return_value = self.entity()
        for _ in range(2):
            self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "Paid")
        self.assertEqual(Notification.objects.filter(user=self.user, category="payment_updates").count(), 1)

    @patch("mobile_api.payment_api.razorpay.Client")
    def test_amount_mismatch_is_rejected(self, client):
        client.return_value.payment.fetch.return_value = self.entity(amount=1)
        self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "Pending")

    def test_invalid_signature_and_foreign_order(self):
        self.assertEqual(self.client.post(self.path, {**self.payload(), "razorpay_signature": "bad"}, format="json").status_code, 400)
        self.client.force_authenticate(User.objects.create_user("other-payer"))
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_online_cancellation_requires_reconciliation(self):
        response = self.client.post(f"/api/v1/orders/shop/{self.order.pk}/cancel/", {"reason": "Please cancel"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.order.refresh_from_db(); self.assertEqual(self.order.payment_status, "Pending")

    def test_failed_native_attempt_keeps_order_recoverable(self):
        from .models import CheckoutSession
        from payments.services import _sync_order_payment
        CheckoutSession.objects.create(user=self.user, order_kind="shop", order_id=self.order.pk, status="completed", address_id=1, cart_fingerprint="test", expires_at=timezone.now())
        _sync_order_payment(self.payment, False)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "Failed")
        self.assertNotEqual(self.order.status, "Cancelled")

    @patch("mobile_api.payment_api.razorpay.Client")
    def test_recovery_after_lost_callback(self, client):
        client.return_value.order.payments.return_value = {"items": [self.entity()]}
        response = self.client.post(self.path, {"action": "recover"}, format="json")
        self.assertEqual(response.data["payment_status"], "Paid")
        self.client.post(self.path, {"action": "cancelled"}, format="json")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "Paid")
