import json
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from orders.models import Order
from .models import SellerDeliveryCharge
from .services import capture_browser_payment


@override_settings(DELHIVERY_API_KEY="test-token", DELHIVERY_PICKUP_LOCATION="Registered warehouse")
class LaunchRegressionTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            user=User.objects.create_user("launch-test"), total_price="100.00",
            payment_method="online", payment_status="Paid", razorpay_order_id="order_test",
        )
        self.charge = SellerDeliveryCharge.objects.create(
            parcel_order=self.order, provider="delhivery", origin_pincode="243638",
            destination_pincode="110001", chargeable_weight_grams=500,
        )

    @patch("payments.services.razorpay.Client")
    def test_signature_alone_cannot_mark_authorized_or_mismatched_payment_captured(self, client):
        valid = {"status": "captured", "order_id": "order_test", "amount": 10000, "currency": "INR"}
        for field, value in (("status", "authorized"), ("order_id", "another_order"),
                             ("amount", 1), ("currency", "USD")):
            with self.subTest(field=field):
                client.return_value.payment.fetch.return_value = {**valid, field: value}
                with self.assertRaises(ValueError):
                    capture_browser_payment(self.order, "order_test", "pay_test", "signature")
                self.assertFalse(self.order.paymenttransactions.exists())

    @patch("orders.shipping.requests.post")
    def test_booking_worker_books_paid_mobile_order_once(self, post):
        response = Mock()
        response.json.return_value = {"packages": [{"waybill": "123456"}]}
        post.return_value = response
        for _ in range(2):
            call_command("book_delhivery_shipments", stdout=StringIO(), stderr=StringIO())
        post.assert_called_once()
        payload = json.loads(post.call_args.kwargs["data"]["data"])
        self.assertEqual(payload["shipments"][0]["payment_mode"], "Pre-paid")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.awb_number, "123456")

    @patch("orders.shipping.requests.post")
    def test_worker_skips_unpaid_and_ambiguous_shipments(self, post):
        self.order.payment_status = "Pending"
        self.order.save()
        call_command("book_delhivery_shipments", stdout=StringIO(), stderr=StringIO())
        self.order.payment_status = "Paid"
        self.order.save()
        self.charge.carrier_status = "manifestation_failed"
        self.charge.save()
        call_command("book_delhivery_shipments", stdout=StringIO(), stderr=StringIO())
        post.assert_not_called()
