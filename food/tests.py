from decimal import Decimal
from io import BytesIO
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import SellerProfile
from payments.models import PaymentTransaction
from PIL import Image
from rest_framework.test import APIClient
from addresses.models import Address

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
        seller = SellerProfile.objects.create(user=owner, store_name="Test Kitchen", business_segment="food", business_category="Restaurant", status="approved")
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

    def menu_payload(self):
        return {
            "section": self.option.item.section_id, "name": "Paneer meal",
            "description": "Fresh paneer and rice", "food_type": "veg",
            "is_available": "on", "accepts_notes": "on",
            "options-TOTAL_FORMS": "3", "options-INITIAL_FORMS": "0",
            "options-MIN_NUM_FORMS": "0", "options-MAX_NUM_FORMS": "1000",
            "options-0-name": "Regular", "options-0-price": "100.00",
            "options-0-is_available": "on",
            "options-1-name": "Regular", "options-1-is_available": "on",
            "options-2-name": "Regular", "options-2-is_available": "on",
        }

    def test_seller_save_then_customer_view_and_purchase(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("food_seller_add_item")).status_code, 200)
        response = self.client.post(reverse("food_seller_add_item"), self.menu_payload())
        self.assertRedirects(response, reverse("food_seller_menu"))
        item = MenuItem.objects.get(name="Paneer meal")
        option = item.options.get()
        self.assertEqual(option.price, Decimal("100.00"))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("food_restaurant", args=[self.restaurant.slug])), item.name)
        self.client.post(reverse("food_cart_add", args=[option.pk]), {"quantity": 2})
        self.assertContains(self.client.get(reverse("food_cart")), item.name)
        response = self.client.post(reverse("food_checkout"), {
            "full_name": "Buyer", "phone": "9999999999", "address": "Market Road",
            "city": "Sahaswan", "state": "UP", "pincode": "243638",
            "latitude": "28.074000", "longitude": "78.751000",
            "gps_accuracy_meters": "12", "gps_captured_at": timezone.now().isoformat(),
            "payment_method": "cod",
        })
        order = FoodOrder.objects.get()
        self.assertRedirects(response, reverse("food_order_success", args=[order.pk]))
        self.assertEqual(order.items.get().menu_item, item)
        self.assertEqual(order.items.get().quantity, 2)
        from mobile_api.models import Notification
        self.assertEqual(Notification.objects.filter(user=self.owner, title="New seller order").count(), 1)
        self.assertFalse(self.client.session["food_cart"]["items"])
        self.assertContains(self.client.get(reverse("food_orders")), item.name)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("food_seller_orders")), item.name)

    def test_seller_cannot_save_without_a_price_option(self):
        self.client.force_login(self.owner)
        payload = self.menu_payload()
        payload["options-0-price"] = ""
        response = self.client.post(reverse("food_seller_add_item"), payload)
        self.assertContains(response, "Add at least one size and price.")
        self.assertFalse(MenuItem.objects.filter(name="Paneer meal").exists())

    def test_seller_cannot_delete_last_price_option(self):
        self.client.force_login(self.owner)
        payload = self.menu_payload()
        payload.update({"options-INITIAL_FORMS": "1", "options-0-id": self.option.pk,
                        "options-0-DELETE": "on"})
        response = self.client.post(reverse("food_seller_edit_item", args=[self.option.item_id]), payload)
        self.assertContains(response, "Add at least one size and price.")
        self.assertTrue(MenuItemOption.objects.filter(pk=self.option.pk).exists())

    def test_seller_can_edit_and_cannot_set_nonpositive_price(self):
        self.client.force_login(self.owner)
        payload = self.menu_payload()
        payload.update({"options-INITIAL_FORMS": "1", "options-0-id": self.option.pk})
        url = reverse("food_seller_edit_item", args=[self.option.item_id])
        self.assertRedirects(self.client.post(url, payload), reverse("food_seller_menu"))
        self.option.refresh_from_db()
        self.assertEqual(self.option.price, Decimal("100.00"))
        for price in ("0", "-10"):
            payload["options-0-price"] = price
            response = self.client.post(url, payload)
            self.assertContains(response, "Ensure this value is greater than or equal to")
            self.option.refresh_from_db()
            self.assertEqual(self.option.price, Decimal("100.00"))

    def test_mobile_photo_save_view_cart_quote_and_purchase(self):
        api = APIClient()
        api.force_authenticate(self.owner)
        photo = BytesIO()
        Image.new("RGB", (4, 4), "red").save(photo, format="PNG")
        with tempfile.TemporaryDirectory() as media, override_settings(
            MEDIA_ROOT=media,
            STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
        ):
            response = api.post("/api/v1/partners/seller/food/products/new/", {
                "name": "Photo meal", "section_name": "Lunch", "food_type": "veg",
                "option_name": "Regular", "option_price": "100.00", "is_available": "True",
                "image": SimpleUploadedFile("meal.png", photo.getvalue(), content_type="image/png"),
            }, format="multipart")
            self.assertEqual(response.status_code, 200, response.data)
            item = MenuItem.objects.get(name="Photo meal")
            self.assertTrue(item.image.storage.exists(item.image.name))
            api.force_authenticate(self.user)
            response = api.get(reverse("mobile-restaurant-detail", args=[self.restaurant.slug]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Photo meal")
            self.assertContains(response, item.image.name)
            response = api.post(reverse("mobile-food-cart-add"), {
                "option_id": item.options.get().pk, "quantity": 2,
            }, format="json")
            self.assertIn(response.status_code, (200, 201), response.data)
            address = Address.objects.create(
                user=self.user, full_name="Buyer", phone="9999999999",
                address_line_1="Market Road", city="Sahaswan", state="UP", pincode="243638",
            )
            quote = api.post(reverse("mobile-checkout-quote", kwargs={"kind": "food"}), {
                "address_id": address.pk,
                "location": {"latitude": "28.074000", "longitude": "78.751000", "gps_accuracy_meters": 12, "gps_captured_at": timezone.now().isoformat()},
            }, format="json")
            self.assertEqual(quote.status_code, 201, quote.data)
            payload = {"address_id": address.pk, "quote_id": quote.data["quote_id"],
                       "idempotency_key": "food-flow-test", "payment_method": "cod"}
            response = api.post(reverse("mobile-food-checkout"), payload, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            order = FoodOrder.objects.get()
            self.assertEqual(order.items.get().menu_item, item)
            self.assertEqual(order.items.get().quantity, 2)
            self.assertFalse(self.user.food_cart_items.exists())
            repeated = api.post(reverse("mobile-food-checkout"), payload, format="json")
            self.assertIn(repeated.status_code, (200, 201), repeated.data)
            self.assertEqual(FoodOrder.objects.count(), 1)

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
        razorpay_client.return_value.payment.fetch.return_value = {
            "status": "captured", "order_id": order.razorpay_order_id,
            "amount": int(order.total * 100), "currency": "INR",
        }

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

    def test_food_cart_quantity_can_be_updated(self):
        self.client.post(reverse("food_cart_add", args=[self.option.pk]), {"quantity": 1})
        response = self.client.post(
            reverse("food_cart_update", args=[self.option.pk]), {"quantity": 3},
        )
        self.assertRedirects(response, reverse("food_cart"))
        self.assertEqual(
            self.client.session["food_cart"]["items"][str(self.option.pk)]["quantity"], 3,
        )

    def test_pending_online_order_can_be_retried_but_not_prepared(self):
        order = FoodOrder.objects.create(
            user=self.user, restaurant=self.restaurant, full_name="Test Customer",
            phone="9999999999", address="Market Road", city="Sahaswan",
            state="Uttar Pradesh", pincode="243638", subtotal="180.00",
            delivery_fee="20.00", total="200.00", payment_method="online",
            payment_status="Pending", razorpay_order_id="order_retry_food",
        )
        self.client.login(username="customer", password="test-password")
        response = self.client.get(reverse("food_payment_retry", args=[order.pk]))
        self.assertContains(response, "Complete your payment")

        self.client.login(username="owner", password="test-password")
        response = self.client.post(
            reverse("food_seller_update_order", args=[order.pk]), {"status": "accepted"},
        )
        self.assertRedirects(response, reverse("food_seller_orders"))
        order.refresh_from_db()
        self.assertEqual(order.status, "placed")
