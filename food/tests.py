from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import SellerProfile
from payments.models import PaymentTransaction

from .models import (
    FoodOrder, FoodSellerSettlement, FoodServiceArea, MenuItem, MenuItemOption,
    MenuSection, Restaurant,
)


@override_settings(ROOT_URLCONF="config.urls")
class FoodOrderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("customer", password="test-password")
        owner = User.objects.create_user("owner", password="test-password")
        self.owner = owner
        seller = SellerProfile.objects.create(user=owner, store_name="Test Kitchen", business_category="Restaurant", status="approved")
        area, _ = FoodServiceArea.objects.get_or_create(
            pincode="243638", defaults={"city": "Sahaswan"}
        )
        self.restaurant = Restaurant.objects.create(seller=seller, name="Test Kitchen", pincode="243638", latitude="28.073100", longitude="78.750200", gps_accuracy_meters=15, delivery_fee="20.00")
        self.restaurant.service_areas.add(area)
        section = MenuSection.objects.create(restaurant=self.restaurant, name="Main course")
        item = MenuItem.objects.create(restaurant=self.restaurant, section=section, name="Veg Biryani")
        self.option = MenuItemOption.objects.create(item=item, name="Full", price="180.00")

    def test_only_serviceable_pincode_lists_restaurant(self):
        response = self.client.get(reverse("food_home"), {"pincode": "243638"})
        self.assertContains(response, "Test Kitchen")
        response = self.client.get(reverse("food_home"), {"pincode": "110001"})
        self.assertNotContains(response, "Test Kitchen")

    def test_food_checkout_creates_separate_order_with_preferences(self):
        self.client.login(username="customer", password="test-password")
        self.client.post(reverse("food_cart_add", args=[self.option.pk]), {"quantity": 2, "note": "Less spicy"})
        response = self.client.post(reverse("food_checkout"), {
            "full_name": "Test Customer", "phone": "9999999999", "address": "Market Road",
            "city": "Sahaswan", "state": "Uttar Pradesh", "pincode": "243638",
            "latitude": "28.074000", "longitude": "78.751000", "gps_accuracy_meters": "12", "gps_captured_at": timezone.now().isoformat(),
            "include_cutlery": "on", "delivery_note": "Call on arrival", "payment_method": "cod",
        })
        self.assertRedirects(response, reverse("food_order_success", args=[1]))
        order = FoodOrder.objects.get()
        self.assertEqual(order.total, Decimal("420.48"))
        self.assertEqual(order.chargebreakdowns.get().delivery_gst, 0)
        self.assertEqual(order.chargebreakdowns.get().seller_sponsored_delivery, 20)
        self.assertTrue(order.include_cutlery)
        self.assertEqual(order.items.get().customer_note, "Less spicy")

    @patch("payments.services.razorpay.Client")
    def test_online_food_payment_is_captured_and_seller_settlement_is_created(self, razorpay_client):
        razorpay_client.return_value.order.create.return_value = {"id": "order_food_test_1"}
        self.client.login(username="customer", password="test-password")
        self.client.post(reverse("food_cart_add", args=[self.option.pk]), {"quantity": 1})

        response = self.client.post(reverse("food_checkout"), {
            "full_name": "Test Customer", "phone": "9999999999", "address": "Market Road",
            "city": "Sahaswan", "state": "Uttar Pradesh", "pincode": "243638",
            "latitude": "28.074000", "longitude": "78.751000", "gps_accuracy_meters": "12",
            "gps_captured_at": timezone.now().isoformat(), "payment_method": "online",
        })
        self.assertEqual(response.status_code, 200)
        order = FoodOrder.objects.get()
        self.assertEqual(order.razorpay_order_id, "order_food_test_1")

        response = self.client.post(reverse("food_payment_confirm", args=[order.pk]), {
            "razorpay_order_id": "order_food_test_1",
            "razorpay_payment_id": "pay_food_test_1",
            "razorpay_signature": "test-signature",
        })

        self.assertRedirects(response, reverse("food_order_success", args=[order.pk]))
        order.refresh_from_db()
        payment = PaymentTransaction.objects.get(food_order=order)
        breakdown = order.chargebreakdowns.get()
        self.assertEqual(order.payment_status, "Paid")
        self.assertEqual(payment.status, "captured")
        self.assertEqual(payment.provider_payment_id, "pay_food_test_1")
        self.assertEqual(breakdown.delivery_gst, Decimal("0.00"))
        self.assertEqual(breakdown.customer_delivery_charge, Decimal("0.00"))
        self.assertTrue(FoodSellerSettlement.objects.filter(order=order).exists())

    def test_checkout_rejects_unserviceable_pincode(self):
        self.client.login(username="customer", password="test-password")
        self.client.post(reverse("food_cart_add", args=[self.option.pk]))
        response = self.client.post(reverse("food_checkout"), {
            "full_name": "Test Customer", "phone": "9999999999", "address": "Elsewhere",
            "city": "Delhi", "state": "Delhi", "pincode": "110001", "payment_method": "cod",
            "latitude": "28.630000", "longitude": "77.210000", "gps_accuracy_meters": "12", "gps_captured_at": timezone.now().isoformat(),
        })
        self.assertContains(response, "does not deliver")
        self.assertFalse(FoodOrder.objects.exists())

    def test_owner_can_manually_close_and_open_restaurant(self):
        self.client.login(username="owner", password="test-password")

        response = self.client.post(reverse("food_seller_toggle_restaurant"))
        self.assertRedirects(response, reverse("food_seller_menu"))
        self.restaurant.refresh_from_db()
        self.assertFalse(self.restaurant.accepts_orders)

        self.client.post(reverse("food_seller_toggle_restaurant"))
        self.restaurant.refresh_from_db()
        self.assertTrue(self.restaurant.accepts_orders)

    def test_closed_restaurant_rejects_cart_add_and_checkout(self):
        self.client.login(username="customer", password="test-password")
        self.restaurant.accepts_orders = False
        self.restaurant.save(update_fields=["accepts_orders"])

        response = self.client.post(reverse("food_cart_add", args=[self.option.pk]))
        self.assertRedirects(response, reverse("food_home"))
        self.assertFalse(self.client.session.get("food_cart", {}).get("items"))
