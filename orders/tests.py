from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Order


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False, RETURN_WINDOW_DAYS=7)
class ReturnWindowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("return-customer", password="test-password")
        self.order = Order.objects.create(
            user=self.customer,
            full_name="Return Customer",
            phone="9999999999",
            address="Market Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price=Decimal("100.00"),
            status="Delivered",
            payment_method="online",
            payment_status="Paid",
            delivered_at=timezone.now() - timedelta(days=2),
        )
        self.client.login(username="return-customer", password="test-password")

    def test_delivered_order_can_enter_return_flow_within_seven_days(self):
        response = self.client.get(reverse("return_order", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.order.can_request_return)

    def test_expired_return_window_is_rejected(self):
        self.order.delivered_at = timezone.now() - timedelta(days=8)
        self.order.save(update_fields=["delivered_at"])

        response = self.client.get(reverse("return_order", args=[self.order.pk]), follow=True)
        self.assertRedirects(response, reverse("order_detail", args=[self.order.pk]))
        self.assertContains(response, "7-day return window")
        self.order.refresh_from_db()
        self.assertFalse(self.order.can_request_return)
