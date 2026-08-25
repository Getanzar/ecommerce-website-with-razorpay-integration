from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import SellerProfile
from payments.models import PaymentTransaction

from .models import (
    GroceryCategory, GroceryOrder, GroceryProduct, GrocerySellerSettlement,
    GroceryServiceArea, GroceryStore,
)


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False, BREVO_API_KEY="")
class GroceryMarketplaceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("grocery-customer", password="test-password")
        self.owner = User.objects.create_user("kirana-owner", password="test-password")
        seller = SellerProfile.objects.create(user=self.owner, store_name="Local Kirana", business_category="Kirana Store", status="approved", commission_percent=10)
        self.area = GroceryServiceArea.objects.create(pincode="243638", city="Sahaswan", delivery_mode="local")
        self.store = GroceryStore.objects.create(seller=seller, name="Local Kirana", address="Main Market", pincode="243638", latitude="28.073100", longitude="78.750200", gps_accuracy_meters=15, phone="9999999999", delivery_fee=20)
        self.store.service_areas.add(self.area)
        category = GroceryCategory.objects.create(name="Staples", slug="staples")
        self.product = GroceryProduct.objects.create(store=self.store, category=category, name="Premium Atta", unit="5 kg", mrp=300, price=250, stock=10)

    def test_pincode_lists_only_serviceable_open_stores(self):
        response = self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.assertContains(response, "Local Kirana")
        response = self.client.get(reverse("grocery_home"), {"pincode": "110001"})
        self.assertNotContains(response, "Local Kirana")

    def test_checkout_creates_order_and_reduces_stock(self):
        self.client.login(username="grocery-customer", password="test-password")
        self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]), {"quantity": 2})
        response = self.client.post(reverse("grocery_checkout"), {"full_name": "Test Customer", "phone": "9999999999", "address": "Market Road", "city": "Sahaswan", "state": "Uttar Pradesh", "pincode": "243638", "latitude": "28.074000", "longitude": "78.751000", "gps_accuracy_meters": "12", "gps_captured_at": timezone.now().isoformat(), "substitution_preference": "contact", "payment_method": "cod"})
        order = GroceryOrder.objects.get()
        self.assertRedirects(response, reverse("grocery_order_success", args=[order.pk]))
        self.assertEqual(order.total, Decimal("559.00"))
        self.assertEqual(order.chargebreakdowns.get().delivery_gst, 0)
        self.assertEqual(order.chargebreakdowns.get().seller_sponsored_delivery, 20)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    @patch("payments.services.razorpay.Client")
    def test_online_grocery_payment_is_captured_and_seller_settlement_is_created(self, razorpay_client):
        razorpay_client.return_value.order.create.return_value = {"id": "order_grocery_test_1"}
        self.client.login(username="grocery-customer", password="test-password")
        self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]), {"quantity": 2})

        response = self.client.post(reverse("grocery_checkout"), {
            "full_name": "Test Customer", "phone": "9999999999", "address": "Market Road",
            "city": "Sahaswan", "state": "Uttar Pradesh", "pincode": "243638",
            "latitude": "28.074000", "longitude": "78.751000", "gps_accuracy_meters": "12",
            "gps_captured_at": timezone.now().isoformat(), "substitution_preference": "contact",
            "payment_method": "online",
        })
        self.assertEqual(response.status_code, 200)
        order = GroceryOrder.objects.get()
        self.assertEqual(order.razorpay_order_id, "order_grocery_test_1")

        response = self.client.post(reverse("grocery_payment_confirm", args=[order.pk]), {
            "razorpay_order_id": "order_grocery_test_1",
            "razorpay_payment_id": "pay_grocery_test_1",
            "razorpay_signature": "test-signature",
        })

        self.assertRedirects(response, reverse("grocery_order_success", args=[order.pk]))
        order.refresh_from_db()
        payment = PaymentTransaction.objects.get(grocery_order=order)
        breakdown = order.chargebreakdowns.get()
        self.product.refresh_from_db()
        self.assertEqual(order.payment_status, "Paid")
        self.assertEqual(payment.status, "captured")
        self.assertEqual(payment.provider_payment_id, "pay_grocery_test_1")
        self.assertEqual(breakdown.delivery_gst, Decimal("0.00"))
        self.assertEqual(breakdown.customer_delivery_charge, Decimal("0.00"))
        self.assertEqual(self.product.stock, 8)
        self.assertTrue(GrocerySellerSettlement.objects.filter(order=order).exists())

    def test_checkout_requires_fresh_authenticated_gps(self):
        self.client.login(username="grocery-customer", password="test-password")
        self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]), {"quantity": 1})
        response = self.client.post(reverse("grocery_checkout"), {
            "full_name": "Test Customer", "phone": "9999999999", "address": "Market Road",
            "city": "Sahaswan", "state": "Uttar Pradesh", "pincode": "243638",
            "substitution_preference": "contact", "payment_method": "cod",
        })
        self.assertContains(response, "Capture your current GPS location")
        self.assertFalse(GroceryOrder.objects.exists())

    def test_kirana_owner_can_close_and_open_store(self):
        self.client.login(username="kirana-owner", password="test-password")
        self.client.post(reverse("grocery_seller_toggle"))
        self.store.refresh_from_db(); self.assertFalse(self.store.accepts_orders)
        response = self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.assertNotContains(response, "Local Kirana")
        self.client.post(reverse("grocery_seller_toggle"))
        self.store.refresh_from_db(); self.assertTrue(self.store.accepts_orders)

    def test_cart_rejects_products_from_another_store(self):
        other_owner = User.objects.create_user("other-kirana")
        seller = SellerProfile.objects.create(user=other_owner, store_name="Other Store", business_category="Grocery", status="approved")
        other_store = GroceryStore.objects.create(seller=seller, name="Other Store", address="Other", pincode="243638", latitude="28.073200", longitude="78.750300", gps_accuracy_meters=20, phone="8888888888")
        other_store.service_areas.add(self.area)
        other_product = GroceryProduct.objects.create(store=other_store, category=self.product.category, name="Rice", unit="1 kg", mrp=80, price=70, stock=5)
        self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]))
        self.client.post(reverse("grocery_cart_add", args=[other_product.pk]))
        cart = self.client.session["grocery_cart"]
        self.assertEqual(cart["store_id"], self.store.pk)
        self.assertNotIn(str(other_product.pk), cart["items"])

    def test_grocery_cart_is_visible_and_quantity_can_be_updated(self):
        self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]))

        home = self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.assertContains(home, "Grocery cart")
        self.assertContains(home, ">1</span>", html=False)

        response = self.client.post(
            reverse("grocery_cart_update", args=[self.product.pk]),
            {"quantity": 4},
        )
        self.assertRedirects(response, reverse("grocery_cart"))
        self.assertEqual(self.client.session["grocery_cart"]["items"][str(self.product.pk)], 4)

    def test_pending_online_order_can_be_retried_but_not_prepared(self):
        order = GroceryOrder.objects.create(
            user=self.customer, store=self.store, full_name="Test Customer",
            phone="9999999999", address="Market Road", city="Sahaswan",
            state="Uttar Pradesh", pincode="243638", subtotal="250.00",
            delivery_fee="20.00", total="270.00", payment_method="online",
            payment_status="Pending", delivery_mode="local",
            razorpay_order_id="order_retry_grocery",
        )
        self.client.login(username="grocery-customer", password="test-password")
        response = self.client.get(reverse("grocery_payment_retry", args=[order.pk]))
        self.assertContains(response, "Complete your payment")

        self.client.login(username="kirana-owner", password="test-password")
        response = self.client.post(
            reverse("grocery_seller_update_order", args=[order.pk]), {"status": "accepted"},
        )
        self.assertRedirects(response, reverse("grocery_seller_orders"))
        order.refresh_from_db()
        self.assertEqual(order.status, "placed")
