from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import SellerProfile
from groceries.models import GroceryOrder, GroceryServiceArea, GroceryStore

from .models import DeliveryAgentProfile, DeliveryEarning, LocalDelivery
from .services import ensure_grocery_delivery, issue_delivery_otp


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LocalDeliveryTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("local-customer", email="customer@example.com", password="test-password")
        owner = User.objects.create_user("local-seller")
        seller = SellerProfile.objects.create(
            user=owner, store_name="Same Town Store", business_category="Grocery", status="approved"
        )
        self.area = GroceryServiceArea.objects.create(pincode="243638", city="Sahaswan", delivery_mode="local")
        self.store = GroceryStore.objects.create(
            seller=seller, name="Same Town Store", address="Main Market", pincode="243638",
            latitude="28.073100", longitude="78.750200", gps_accuracy_meters=15,
            phone="9999999999", delivery_fee="25.00",
        )
        self.store.service_areas.add(self.area)
        self.order = GroceryOrder.objects.create(
            user=self.customer, store=self.store, full_name="Local Customer", phone="9999999999",
            address="Market Road", city="Sahaswan", state="Uttar Pradesh", pincode="243638",
            latitude="28.074000", longitude="78.751000", gps_accuracy_meters=12,
            subtotal="100.00", delivery_fee="25.00", total="125.00", delivery_mode="local", status="ready",
        )
        self.agent_user = User.objects.create_user("local-agent", password="test-password")
        self.agent = DeliveryAgentProfile.objects.create(
            user=self.agent_user, full_name="Local Rider", phone="8888888888", address="Town Road",
            city="Sahaswan", state="Uttar Pradesh", pincode="243638", vehicle_type="bicycle",
            aadhaar_last4="1234", status="approved", is_online=True,
        )

    def test_only_exact_pincode_agent_sees_and_accepts_job(self):
        delivery = ensure_grocery_delivery(self.order)
        self.assertEqual(str(delivery.pickup_latitude), "28.073100")
        self.assertEqual(str(delivery.customer_latitude), "28.074000")
        self.client.login(username="local-agent", password="test-password")
        response = self.client.get(reverse("delivery_dashboard"))
        self.assertContains(response, "Same Town Store")
        response = self.client.post(reverse("delivery_accept", args=[delivery.pk]))
        self.assertRedirects(response, reverse("delivery_dashboard"))
        delivery.refresh_from_db()
        self.assertEqual(delivery.agent, self.agent)

    def test_agent_from_another_pincode_cannot_accept(self):
        delivery = ensure_grocery_delivery(self.order)
        self.agent.pincode = "110001"
        self.agent.save(update_fields=["pincode"])
        self.client.login(username="local-agent", password="test-password")
        self.client.post(reverse("delivery_accept", args=[delivery.pk]))
        delivery.refresh_from_db()
        self.assertIsNone(delivery.agent)

    def test_different_store_and_customer_pincodes_never_create_job(self):
        self.order.pincode = "110001"
        self.order.save(update_fields=["pincode"])
        self.assertIsNone(ensure_grocery_delivery(self.order))
        self.assertFalse(LocalDelivery.objects.exists())

    def test_nonlocal_grocery_order_never_enters_agent_pool(self):
        self.order.delivery_mode = "delhivery"
        self.order.save(update_fields=["delivery_mode"])
        self.assertIsNone(ensure_grocery_delivery(self.order))
        self.assertFalse(LocalDelivery.objects.exists())

    def test_customer_otp_completes_order_and_records_earning(self):
        delivery = ensure_grocery_delivery(self.order)
        delivery.agent = self.agent
        delivery.status = "out_for_delivery"
        delivery.agent_latitude = "28.073100"
        delivery.agent_longitude = "78.750200"
        delivery.save(update_fields=["agent", "status", "agent_latitude", "agent_longitude"])
        otp = issue_delivery_otp(delivery)
        self.client.login(username="local-agent", password="test-password")
        response = self.client.post(reverse("delivery_complete", args=[delivery.pk]), {"otp": otp})
        self.assertRedirects(response, reverse("delivery_dashboard"))
        delivery.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(delivery.status, "delivered")
        self.assertIsNone(delivery.agent_latitude)
        self.assertIsNone(delivery.agent_longitude)
        self.assertEqual(self.order.status, "delivered")
        self.assertEqual(self.order.payment_status, "Paid")
        self.assertTrue(DeliveryEarning.objects.filter(agent=self.agent, delivery=delivery, amount="25.00").exists())

    def test_assigned_agent_can_share_valid_live_location(self):
        delivery = ensure_grocery_delivery(self.order)
        delivery.agent = self.agent
        delivery.status = "accepted"
        delivery.save(update_fields=["agent", "status"])
        self.client.login(username="local-agent", password="test-password")
        response = self.client.post(reverse("delivery_location_update", args=[delivery.pk]), {
            "latitude": "28.073100", "longitude": "78.750200", "accuracy": "12.8",
        })
        self.assertEqual(response.status_code, 200)
        delivery.refresh_from_db()
        self.assertEqual(str(delivery.agent_latitude), "28.073100")
        self.assertEqual(delivery.location_accuracy_meters, 12)

    def test_location_update_rejects_invalid_coordinates_and_wrong_agent(self):
        delivery = ensure_grocery_delivery(self.order)
        delivery.agent = self.agent
        delivery.status = "accepted"
        delivery.save(update_fields=["agent", "status"])
        self.client.login(username="local-agent", password="test-password")
        response = self.client.post(reverse("delivery_location_update", args=[delivery.pk]), {
            "latitude": "91", "longitude": "78", "accuracy": "10",
        })
        self.assertEqual(response.status_code, 400)
        other_user = User.objects.create_user("other-agent", password="test-password")
        DeliveryAgentProfile.objects.create(
            user=other_user, full_name="Other Rider", phone="7777777777", address="Other",
            city="Sahaswan", state="Uttar Pradesh", pincode="243638", vehicle_type="bicycle",
            aadhaar_last4="5678", status="approved", is_online=True,
        )
        self.client.login(username="other-agent", password="test-password")
        response = self.client.post(reverse("delivery_location_update", args=[delivery.pk]), {
            "latitude": "28", "longitude": "78", "accuracy": "10",
        })
        self.assertEqual(response.status_code, 404)

    def test_only_customer_can_poll_delivery_location(self):
        delivery = ensure_grocery_delivery(self.order)
        delivery.agent = self.agent
        delivery.status = "out_for_delivery"
        delivery.agent_latitude = "28.073100"
        delivery.agent_longitude = "78.750200"
        delivery.save(update_fields=["agent", "status", "agent_latitude", "agent_longitude"])
        stranger = User.objects.create_user("stranger", password="test-password")
        self.client.login(username="stranger", password="test-password")
        self.assertEqual(self.client.get(reverse("delivery_live_location", args=[delivery.public_id])).status_code, 403)
        self.client.login(username="local-customer", password="test-password")
        response = self.client.get(reverse("delivery_live_location", args=[delivery.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["available"])
        self.assertEqual(response.json()["latitude"], 28.0731)

    def test_location_updates_stop_after_delivery(self):
        delivery = ensure_grocery_delivery(self.order)
        delivery.agent = self.agent
        delivery.status = "delivered"
        delivery.save(update_fields=["agent", "status"])
        self.client.login(username="local-agent", password="test-password")
        response = self.client.post(reverse("delivery_location_update", args=[delivery.pk]), {
            "latitude": "28", "longitude": "78", "accuracy": "10",
        })
        self.assertEqual(response.status_code, 409)
