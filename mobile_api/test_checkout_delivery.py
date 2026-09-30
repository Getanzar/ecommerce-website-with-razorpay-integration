from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from addresses.models import Address
from cart.models import Cart, CartItem
from delivery.models import DeliveryAgentProfile, LocalDelivery
from food.models import FoodCartItem, FoodOrder, FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant
from groceries.models import GroceryCartItem, GroceryCategory, GroceryOrder, GroceryProduct, GroceryServiceArea, GroceryStore
from orders.models import Order
from payments.models import PaymentTransaction
from payments.services import _sync_order_payment
from products.models import Category, Product, ProductColor, ProductVariant
from .models import Notification


class CheckoutDeliveryTests(APITestCase):
    def setUp(self):
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Live network forbidden in delivery tests"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.buyer = User.objects.create_user("delivery-buyer")
        self.owner = User.objects.create_user("delivery-seller")
        self.seller = SellerProfile.objects.create(user=self.owner, store_name="Local seller", status="approved", business_segment="food", business_category="Restaurant", business_pincode="243638", business_latitude="28.073100", business_longitude="78.750200")
        self.rider_user = User.objects.create_user("delivery-rider")
        self.rider = DeliveryAgentProfile.objects.create(user=self.rider_user, status="approved", is_online=True, pincode="243638")
        self.address = Address.objects.create(user=self.buyer, full_name="Buyer", phone="9999999999", address_line_1="Market Road", city="Sahaswan", state="UP", pincode="243638")
        self.location = {"latitude": "28.074000", "longitude": "78.751000", "gps_accuracy_meters": 12, "gps_captured_at": timezone.now().isoformat()}
        self.client.force_authenticate(self.buyer)

    def seed(self, kind):
        if kind == "shop":
            self.seller.business_segment = 'shop'
            self.seller.business_category = "Clothing"
            self.seller.save()
            category = Category.objects.create(name="Clothes", slug="delivery-clothes")
            product = Product.objects.create(seller=self.seller, category=category, name="Shirt", price=100, moderation_status="approved")
            color = ProductColor.objects.create(product=product, name="Blue")
            variant = ProductVariant.objects.create(product=product, color=color, size="M", stock=5)
            cart, _ = Cart.objects.get_or_create(user=self.buyer)
            CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)
        elif kind == "food":
            store = Restaurant.objects.create(seller=self.seller, name="Kitchen", pincode="243638", latitude="28.073100", longitude="78.750200", delivery_fee=20)
            area, _ = FoodServiceArea.objects.get_or_create(pincode="243638")
            store.service_areas.add(area)
            section = MenuSection.objects.create(restaurant=store, name="Lunch")
            item = MenuItem.objects.create(restaurant=store, section=section, name="Meal")
            option = MenuItemOption.objects.create(item=item, price=100)
            FoodCartItem.objects.create(user=self.buyer, option=option)
        else:
            self.seller.business_segment = 'grocery'
            self.seller.business_category = "Grocery"
            self.seller.save()
            store = GroceryStore.objects.create(seller=self.seller, name="Grocer", pincode="243638", latitude="28.073100", longitude="78.750200", delivery_fee=20)
            area, _ = GroceryServiceArea.objects.get_or_create(pincode="243638", defaults={"delivery_mode": "local"})
            store.service_areas.add(area)
            category = GroceryCategory.objects.create(name="Rice", slug="delivery-rice")
            product = GroceryProduct.objects.create(store=store, category=category, name="Rice", price=100, mrp=110, stock=5, unit="1 kg")
            GroceryCartItem.objects.create(user=self.buyer, product=product)

    def quote(self, kind, location=True):
        data = {"address_id": self.address.pk}
        if location:
            data["location"] = self.location
        return self.client.post(f"/api/v1/checkout/{kind}/quote/", data, format="json")

    def place(self, kind, payment="cod"):
        quote = self.quote(kind)
        self.assertEqual(quote.status_code, 201, quote.data)
        payload = {"address_id": self.address.pk, "quote_id": quote.data["quote_id"], "idempotency_key": f"delivery-{kind}", "payment_method": payment}
        response = self.client.post(f"/api/v1/checkout/{kind}/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        repeated = self.client.post(f"/api/v1/checkout/{kind}/", payload, format="json")
        self.assertEqual(repeated.status_code, 200, repeated.data)
        model = {"shop": Order, "food": FoodOrder, "grocery": GroceryOrder}[kind]
        order = model.objects.get(pk=response.data["id"])
        self.assertEqual(order.latitude, Decimal(self.location["latitude"]))
        self.assertEqual(order.sellerdeliverycharges.count(), 1)
        return order

    def assert_rider_can_claim(self):
        job = LocalDelivery.objects.get()
        self.assertEqual(job.customer_latitude, Decimal(self.location["latitude"]))
        self.assertEqual(Notification.objects.filter(user=self.owner, title="New seller order").count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.rider_user, title="Delivery available").count(), 1)
        self.client.force_authenticate(self.rider_user)
        response = self.client.post(f"/api/v1/partners/rider/jobs/{job.pk}/accept/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        job.refresh_from_db()
        self.assertEqual(job.agent, self.rider)

    def test_local_shop_cod_dispatches_once(self):
        self.seed("shop")
        self.place("shop")
        self.assert_rider_can_claim()

    def local_service_flow(self, kind, middle):
        self.seed(kind)
        order = self.place(kind)
        self.assertFalse(LocalDelivery.objects.exists())
        self.client.force_authenticate(self.owner)
        for status in ("accepted", middle, "ready"):
            response = self.client.patch(f"/api/v1/partners/seller/{kind}/orders/{order.pk}/", {"status": status}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assert_rider_can_claim()

    def test_food_order_reaches_rider_after_preparation(self):
        self.local_service_flow("food", "preparing")

    def test_grocery_order_reaches_rider_after_packing(self):
        self.local_service_flow("grocery", "packing")

    @patch("payments.services.create_razorpay_order", return_value={"id": "order_delivery_test"})
    def test_online_dispatch_and_seller_alert_wait_for_payment(self, provider):
        self.seed("shop")
        order = self.place("shop", "online")
        self.assertFalse(LocalDelivery.objects.exists())
        self.assertFalse(Notification.objects.filter(user=self.owner, title="New seller order").exists())
        payment = PaymentTransaction.objects.get(parcel_order=order)
        _sync_order_payment(payment, True)
        _sync_order_payment(payment, True)
        self.assert_rider_can_claim()

    def test_local_quote_requires_valid_fresh_location(self):
        self.seed("food")
        self.assertEqual(self.quote("food", location=False).status_code, 409)
        for changes in ({"latitude": "91"}, {"gps_accuracy_meters": 501}, {"gps_captured_at": (timezone.now() - timedelta(minutes=6)).isoformat()}):
            with self.subTest(changes=changes):
                original = self.location.copy()
                self.location.update(changes)
                self.assertEqual(self.quote("food").status_code, 400)
                self.location = original
        self.assertFalse(FoodOrder.objects.exists())

    def test_changed_address_requires_new_quote(self):
        self.seed("food")
        quote = self.quote("food")
        self.address.address_line_1 = "Different address"
        self.address.save()
        response = self.client.post("/api/v1/checkout/food/", {"address_id": self.address.pk, "quote_id": quote.data["quote_id"], "idempotency_key": "changed"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(FoodOrder.objects.exists())

    def test_submitted_items_cannot_bypass_the_quote(self):
        self.seed("food")
        quote = self.quote("food")
        option = MenuItemOption.objects.get()
        response = self.client.post("/api/v1/checkout/food/", {
            "address_id": self.address.pk, "quote_id": quote.data["quote_id"], "idempotency_key": "changed-items",
            "items": [{"option_id": option.pk, "quantity": 20}],
        }, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(FoodOrder.objects.exists())

    def test_missing_pickup_does_not_mark_legacy_order_ready(self):
        self.seed("food")
        order = self.place("food")
        order.latitude = None
        order.status = "preparing"
        order.save()
        self.client.force_authenticate(self.owner)
        response = self.client.patch(f"/api/v1/partners/seller/food/orders/{order.pk}/", {"status": "ready"}, format="json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "preparing")
        self.assertFalse(LocalDelivery.objects.exists())
