from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import SellerProfile
from .models import FoodOrder, FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant


@override_settings(ROOT_URLCONF="config.urls")
class FoodOrderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("customer", password="test-password")
        owner = User.objects.create_user("owner", password="test-password")
        seller = SellerProfile.objects.create(user=owner, store_name="Test Kitchen", business_category="Restaurant", status="approved")
        area, _ = FoodServiceArea.objects.get_or_create(
            pincode="243638", defaults={"city": "Sahaswan"}
        )
        self.restaurant = Restaurant.objects.create(seller=seller, name="Test Kitchen", delivery_fee="20.00")
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
            "include_cutlery": "on", "delivery_note": "Call on arrival", "payment_method": "cod",
        })
        self.assertRedirects(response, reverse("food_order_success", args=[1]))
        order = FoodOrder.objects.get()
        self.assertEqual(order.total, 416)
        self.assertTrue(order.include_cutlery)
        self.assertEqual(order.items.get().customer_note, "Less spicy")

    def test_checkout_rejects_unserviceable_pincode(self):
        self.client.login(username="customer", password="test-password")
        self.client.post(reverse("food_cart_add", args=[self.option.pk]))
        response = self.client.post(reverse("food_checkout"), {
            "full_name": "Test Customer", "phone": "9999999999", "address": "Elsewhere",
            "city": "Delhi", "state": "Delhi", "pincode": "110001", "payment_method": "cod",
        })
        self.assertContains(response, "does not deliver")
        self.assertFalse(FoodOrder.objects.exists())
