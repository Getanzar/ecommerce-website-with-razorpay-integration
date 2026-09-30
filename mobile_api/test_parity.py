"""Cross-service checks for the mobile payment and seller entry points."""
import hashlib
import hmac
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from food.models import FoodOrder, Restaurant
from groceries.models import GroceryCategory, GroceryOrder, GroceryProduct, GroceryStore
from payments.services import create_payment_transaction


class ServiceParityTests(APITestCase):
    def test_grocery_multipart_product_upload_and_edit(self):
        self.store.latitude = "28.000000"
        self.store.longitude = "78.000000"
        self.store.save()
        category = GroceryCategory.objects.create(name="Upload category", slug="upload")
        self.client.force_authenticate(self.seller_user)
        image = BytesIO()
        Image.new("RGB", (4, 4), "red").save(image, format="PNG")
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
            data = {"category": str(category.pk), "name": "Uploaded rice", "unit": "1 kg", "mrp": "120", "price": "100", "gst_rate": "0", "stock": "5", "is_active": "True", "image": SimpleUploadedFile("rice.png", image.getvalue(), content_type="image/png")}
            response = self.client.post("/api/v1/partners/seller/grocery/products/new/", data, format="multipart")
            self.assertEqual(response.status_code, 200, response.data)
            product = GroceryProduct.objects.get(store=self.store, name="Uploaded rice")
            self.assertTrue(product.image.storage.exists(product.image.name))
            data.pop("image")
            data["name"] = "Edited rice"
            response = self.client.post(f"/api/v1/partners/seller/grocery/products/{product.pk}/edit/", data, format="multipart")
            self.assertEqual(response.status_code, 200, response.data)
            product.refresh_from_db()
            self.assertEqual(product.name, "Edited rice")

    def test_grocery_store_settings_multipart_save(self):
        self.client.force_authenticate(self.seller_user)
        data = {"name": "Updated grocer", "address": "Market", "pincode": "243638", "phone": "9876543210", "latitude": "28.000000", "longitude": "78.000000", "gps_accuracy_meters": "20", "gps_captured_at": timezone.now().isoformat(), "minimum_order": "0", "delivery_fee": "0", "estimated_delivery_minutes": "30"}
        response = self.client.post("/api/v1/partners/seller/grocery/store/", data, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Updated grocer")

    def setUp(self):
        cache.clear()
        self.buyer = User.objects.create_user("parity-buyer")
        self.seller_user = User.objects.create_user("parity-seller")
        self.seller = SellerProfile.objects.create(user=self.seller_user, store_name="Store", business_segment="grocery", business_category="Grocery", status="approved")
        self.store = GroceryStore.objects.create(seller=self.seller, name="Grocer")
        self.restaurant = Restaurant.objects.create(seller=self.seller, name="Kitchen")

    @override_settings(RAZORPAY_KEY_ID="key", RAZORPAY_KEY_SECRET="secret")
    @patch("mobile_api.payment_api.razorpay.Client")
    def test_food_and_grocery_capture_recovery_and_ownership(self, provider):
        for kind, model, owner in (
            ("food", FoodOrder, {"restaurant": self.restaurant}),
            ("grocery", GroceryOrder, {"store": self.store}),
        ):
            with self.subTest(kind=kind):
                order = model.objects.create(user=self.buyer, subtotal=100, total=100, payment_method="online", **owner)
                provider_order = f"order_{kind}"
                payment_id = f"pay_{kind}"
                create_payment_transaction(order, provider_order)
                entity = {"id": payment_id, "order_id": provider_order, "amount": 10000, "currency": "INR", "status": "captured"}
                provider.return_value.payment.fetch.return_value = entity
                provider.return_value.order.payments.return_value = {"items": [entity]}
                path = f"/api/v1/orders/{kind}/{order.pk}/payment/"
                self.client.force_authenticate(self.seller_user)
                self.assertEqual(self.client.get(path).status_code, 404)
                self.client.force_authenticate(self.buyer)
                signature = hmac.new(b"secret", f"{provider_order}|{payment_id}".encode(), hashlib.sha256).hexdigest()
                response = self.client.post(path, {"action": "verify", "razorpay_order_id": provider_order, "razorpay_payment_id": payment_id, "razorpay_signature": signature}, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["payment_status"], "Paid")
                response = self.client.post(path, {"action": "recover"}, format="json")
                self.assertEqual(response.data["payment_status"], "Paid")
                order.refresh_from_db()
                self.assertEqual(order.payment_status, "Paid")

    def test_grocery_workspace_stock_availability_and_order_guards(self):
        category = GroceryCategory.objects.create(name="Rice", slug="rice")
        product = GroceryProduct.objects.create(store=self.store, category=category, name="Rice", unit="1 kg", price=100, mrp=100, stock=5)
        order = GroceryOrder.objects.create(user=self.buyer, store=self.store, subtotal=100, total=100, payment_method="online")
        prefix = "/api/v1/partners/seller/grocery/"
        self.client.force_authenticate(self.seller_user)
        for section in ("orders", "catalog", "payouts"):
            self.assertEqual(self.client.get(f"{prefix}{section}/").status_code, 200)
        self.assertEqual(self.client.patch(f"{prefix}catalog/{product.pk}/", {"stock": 9}, format="json").status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.stock, 9)
        self.assertEqual(self.client.patch(f"{prefix}availability/", {"accepts_orders": False}, format="json").status_code, 200)
        self.store.refresh_from_db()
        self.assertFalse(self.store.accepts_orders)
        path = f"{prefix}orders/{order.pk}/"
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 400)
        order.payment_status = "Paid"
        order.save(update_fields=["payment_status"])
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 200)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.patch(f"{prefix}catalog/{product.pk}/", {"stock": 0}, format="json").status_code, 404)
        product.refresh_from_db()
        self.assertEqual(product.stock, 9)
