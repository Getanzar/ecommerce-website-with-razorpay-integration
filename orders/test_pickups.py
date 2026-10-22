from unittest.mock import Mock, patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import requests
from accounts.models import SellerProfile
from products.models import Category, Product
from payments.models import SellerDeliveryCharge, DelhiveryPickupRequest
from orders.models import Order, OrderItem
from orders.pickups import ensure_seller_warehouse, parcel_ready, schedule_charge_pickup


@override_settings(DELHIVERY_API_KEY="test-token")
class PickupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("seller", email="seller@example.com")
        self.seller = SellerProfile.objects.create(user=self.user, store_name="Delhi shop", status="approved", business_segment="shop", business_address="Delhi market", business_phone="9999999999", business_pincode="110001", business_gps_verified_at=timezone.now(), delhivery_pickup_name="Delhi warehouse")
        self.order = Order.objects.create(user=User.objects.create_user("buyer"), total_price=100, payment_method="online", payment_status="Paid", status="Processing", pincode="243001")
        product = Product.objects.create(category=Category.objects.create(name="Merchandise", slug="merch"), seller=self.seller, name="Shirt", slug="shirt", price=100)
        self.item = OrderItem.objects.create(order=self.order, product=product, product_name="Shirt", quantity=1, price=100, fulfillment_status="packed")
        self.charge = SellerDeliveryCharge.objects.create(parcel_order=self.order, seller=self.seller, provider="delhivery", awb_number="12345", origin_pincode="110001", destination_pincode="243001", pickup_location_name="Delhi warehouse")

    def response(self, payload):
        return Mock(status_code=200, ok=True, json=Mock(return_value=payload))

    @patch("orders.pickups.requests.post")
    def test_packed_parcel_schedules_from_actual_seller_city(self, post):
        post.return_value = self.response({"pickup_id": 456})
        pickup = schedule_charge_pickup(self.charge.pk)
        self.assertEqual(pickup.status, "scheduled")
        self.assertEqual(post.call_args.kwargs["json"]["pickup_location"], "Delhi warehouse")
        self.assertEqual(pickup.provider_pickup_id, "456")

    @patch("orders.pickups.requests.post")
    def test_unpaid_or_partially_packed_parcel_cannot_request_pickup(self, post):
        self.order.payment_status = "Pending"
        self.order.save()
        self.assertIsNone(schedule_charge_pickup(self.charge.pk))
        self.order.payment_status = "Paid"
        self.order.save()
        OrderItem.objects.create(order=self.order, product=self.item.product, product_name="Other", price=100, fulfillment_status="accepted")
        self.assertIsNone(schedule_charge_pickup(self.charge.pk))
        post.assert_not_called()

    @patch("orders.pickups.requests.get")
    @patch("orders.pickups.requests.post")
    def test_repeated_packed_event_does_not_duplicate_pickup(self, post, get):
        post.return_value = self.response({"pickup_id": 456})
        get.return_value = self.response({"ShipmentData": [{"Shipment": {"AWB": "12345", "Status": {"Status": "Manifested"}}}]})
        first = schedule_charge_pickup(self.charge.pk)
        second = schedule_charge_pickup(self.charge.pk)
        self.assertEqual(first.pk, second.pk)
        post.assert_called_once()

    @patch("orders.pickups.requests.post", side_effect=requests.Timeout("lost response"))
    def test_timeout_requires_review_even_on_manual_retry(self, post):
        pickup = schedule_charge_pickup(self.charge.pk)
        self.assertEqual(pickup.status, "review")
        self.assertEqual(schedule_charge_pickup(self.charge.pk, retry=True).pk, pickup.pk)
        post.assert_called_once()

    @patch("orders.pickups.requests.get")
    @patch("orders.pickups.requests.post")
    def test_new_seller_address_is_registered_once(self, post, get):
        self.seller.delhivery_pickup_name = ""
        self.seller.save()
        get.return_value = self.response({"delivery_codes": [{"postal_code": {"pin": 110001, "pickup": "Y", "city": "Delhi", "state_code": "DL"}}]})
        post.return_value = self.response({"success": True})
        name = ensure_seller_warehouse(self.seller)
        self.assertEqual(ensure_seller_warehouse(self.seller), name)
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"]["address"], "Delhi market")
        self.assertEqual(post.call_args.kwargs["json"]["pin"], "110001")

    @patch("orders.pickups.schedule_charge_pickup")
    def test_web_packing_queues_pickup_after_commit(self, schedule):
        self.item.fulfillment_status = "accepted"
        self.item.save()
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("seller_update_order_item", args=[self.item.pk]), {"status": "packed"})
        self.assertEqual(response.status_code, 302)
        schedule.assert_called_once_with(self.charge.pk, retry=False)

    def test_other_seller_cannot_trigger_pickup(self):
        other = User.objects.create_user("other")
        SellerProfile.objects.create(user=other, status="approved", business_segment="shop", store_name="Other")
        self.client.force_login(other)
        response = self.client.post(reverse("seller_request_pickup", args=[self.item.pk]))
        self.assertEqual(response.status_code, 404)

    @patch("orders.pickups.requests.post")
    def test_explicit_authentication_failure_can_be_retried(self, post):
        post.return_value = Mock(status_code=401, ok=False, json=Mock(return_value={"error": "Unauthorized"}))
        failed = schedule_charge_pickup(self.charge.pk)
        self.assertEqual(failed.status, "failed")
        post.return_value = self.response({"pickup_id": 789})
        scheduled = schedule_charge_pickup(self.charge.pk, retry=True)
        self.assertEqual(scheduled.status, "scheduled")
        self.assertNotEqual(scheduled.pk, failed.pk)

    @patch("orders.pickups.requests.post", side_effect=requests.Timeout("lost registration"))
    @patch("orders.pickups.requests.get")
    def test_lost_warehouse_response_is_not_registered_twice(self, get, post):
        from orders.pickups import PickupSetupError
        self.seller.delhivery_pickup_name = ""
        self.seller.save()
        get.return_value = self.response({"delivery_codes": [{"postal_code": {"pin": 110001, "pickup": "Y", "city": "Delhi", "state_code": "DL"}}]})
        for _ in range(2):
            with self.assertRaises(PickupSetupError):
                ensure_seller_warehouse(self.seller)
        post.assert_called_once()

    @patch("orders.pickups.requests.get")
    @patch("orders.pickups.requests.post")
    def test_confirmed_collection_releases_location_for_later_order(self, post, get):
        post.return_value = self.response({"pickup_id": 456})
        first = schedule_charge_pickup(self.charge.pk)
        self.order.pk = None
        self.order.save()
        OrderItem.objects.create(order=self.order, product=self.item.product, product_name="Next shirt", price=100, fulfillment_status="packed")
        charge = SellerDeliveryCharge.objects.create(parcel_order=self.order, seller=self.seller, provider="delhivery", awb_number="67890", pickup_location_name="Delhi warehouse")
        get.return_value = self.response({"ShipmentData": [{"Shipment": {"AWB": "12345", "Status": {"Status": "In Transit"}}}]})
        post.return_value = self.response({"pickup_id": 789})
        second = schedule_charge_pickup(charge.pk)
        first.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(first.status, "completed")
        self.assertEqual(self.item.fulfillment_status, "shipped")
        self.assertNotEqual(first.pk, second.pk)
