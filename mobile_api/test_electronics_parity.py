from io import BytesIO
from decimal import Decimal

from django.contrib.auth.models import User, Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from food.models import Restaurant, MenuSection
from orders.models import Order, SellerSettlement
from products.models import Category, Product, ProductColor, ProductVariant, SubCategory


class ElectronicsParityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user("accessories-seller")
        self.seller = SellerProfile.objects.create(user=self.user, store_name="Phone covers", status="approved", business_segment="shop", business_category="Mobile accessories")
        self.path = "/api/v1/partners/seller/electronics/mobile_accessory/new/"

    def photo(self):
        image = BytesIO()
        Image.new("RGB", (8, 8)).save(image, "PNG")
        return SimpleUploadedFile("cover.png", image.getvalue(), content_type="image/png")

    def test_category_icons_and_existing_accessories_in_electronics(self):
        category = Category.objects.create(name="Mobile accessories", slug="mobile-accessories")
        sub = SubCategory.objects.create(category=category, name="Mobile cover")
        product = Product.objects.create(seller=self.seller, category=category, subcategory=sub, name="Legacy phone cover", price=100, product_type="accessory")
        color = ProductColor.objects.create(product=product, name="Blue")
        variant = ProductVariant.objects.create(product=product, color=color, size="Standard", stock=2)
        response = self.client.get("/api/v1/categories/")
        electronics = next(row for row in response.data if row["slug"] == "electronics")
        self.assertEqual(electronics["icon"], "cpu")
        self.assertEqual(len(electronics["electronics_types"]), 5)
        self.assertIn(product.pk, [row["id"] for row in self.client.get("/api/v1/products/?category=electronics&electronics_type=mobile_accessory").data["results"]])
        self.assertNotIn(product.pk, [row["id"] for row in self.client.get("/api/v1/products/?category=electronics&electronics_type=laptop").data["results"]])
        variant.stock = 0
        variant.save()
        self.assertNotIn(product.pk, [row["id"] for row in self.client.get("/api/v1/products/?category=electronics").data["results"]])

    def test_seller_schema_is_category_specific_and_permissions_checked(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)
        self.client.force_authenticate(self.user)
        fields = {row["name"] for row in self.client.get(self.path).data["fields"]}
        self.assertIn("spec_compatible_devices", fields)
        self.assertNotIn("spec_ram", fields)
        self.assertNotIn("gender", fields)
        self.assertEqual(self.client.get("/api/v1/partners/seller/electronics/laptop/new/").status_code, 403)
        workspace = self.client.get("/api/v1/partners/seller/").data
        self.assertEqual([row["key"] for row in workspace["electronics_types"]], ["mobile_accessory"])

    def test_generic_builder_does_not_offer_electronics_or_crash_on_missing_category(self):
        self.client.force_authenticate(self.user)
        path = "/api/v1/partners/seller/products/new/"
        fields = {row["name"]: row for row in self.client.get(path).data["fields"]}
        choices = {key for key, label in fields["product_type"]["choices"]}
        self.assertNotIn("mobile", choices)
        self.assertIn("shirt", choices)
        response = self.client.post(path, {})
        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_upload_and_edit_use_same_model_specs_and_review_as_website(self):
        self.client.force_authenticate(self.user)
        data = {"name": "Phone cover", "description": "Protective phone cover", "price": "100", "gst_rate": "18", "brand": "Test", "model_number": "C1", "warranty": "No warranty", "color": "Blue", "quantity": "4", "package_weight_grams": "100", "package_length_cm": "15", "package_width_cm": "10", "package_height_cm": "2", "spec_accessory_type": "Phone case", "spec_compatible_devices": "Model X", "spec_connector": "Not applicable", "spec_material": "Silicone", "image": self.photo()}
        response = self.client.post(self.path, data, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(pk=response.data["id"])
        self.assertEqual(product.seller, self.seller)
        self.assertFalse(product.is_active)
        self.assertEqual(product.moderation_status, "pending")
        self.assertEqual(product.variants.get().stock, 4)
        self.assertEqual(product.specifications["Compatible devices"], "Model X")
        edit_path = f"/api/v1/partners/seller/products/{product.pk}/edit/"
        fields = {row["name"]: row for row in self.client.get(edit_path).data["fields"]}
        self.assertTrue(fields["quantity"]["disabled"])
        edit = {name: row["value"] for name, row in fields.items() if row["type"] != "image"}
        edit.update(spec_material="TPU", quantity="999")
        self.assertEqual(self.client.post(edit_path, edit).status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.stock, 4)
        self.assertEqual(product.specifications["Material"], "TPU")
        other = User.objects.create_user("other-buyer")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(edit_path).status_code, 404)

    def test_finance_uses_net_payout_and_never_another_sellers_money(self):
        self.client.force_authenticate(self.user)
        order = Order.objects.create(user=self.user, total_price=100, payment_method="online", payment_status="Paid")
        SellerSettlement.objects.create(seller=self.seller, order=order, gross_amount=100, commission_amount=10, net_amount=90, deductions_amount=5, delivery_charge=10, tcs_amount=1, payment_method="online", scheduled_for=timezone.now())
        workspace = self.client.get("/api/v1/partners/seller/")
        self.assertEqual(workspace.status_code, 200, workspace.data)
        self.assertEqual(Decimal(workspace.data["finance"]["scheduled"]), Decimal("74"))
        payouts = self.client.get("/api/v1/partners/seller/shop/payouts/").data["results"]
        self.assertEqual(payouts[0]["amount"], "74.00")
        self.assertEqual(payouts[0]["delivery_charge"], "10.00")

    def test_restaurant_sections_are_food_only_and_idempotent(self):
        self.client.force_authenticate(self.user)
        path = "/api/v1/partners/seller/food/sections/new/"
        self.assertEqual(self.client.get(path).status_code, 403)
        self.seller.business_segment = "food"
        self.seller.save()
        restaurant = Restaurant.objects.create(seller=self.seller, name="Kitchen", pincode="243638")
        self.assertEqual(self.client.get(path).status_code, 200)
        for expected in (201, 200):
            response = self.client.post(path, {"name": "Fresh drinks", "display_order": 5})
            self.assertEqual(response.status_code, expected, response.data)
        self.assertEqual(MenuSection.objects.filter(restaurant=restaurant, name="Fresh drinks").count(), 1)


class AdminWorkspacePermissionTests(APITestCase):
    def test_only_explicit_operations_permission_can_read_native_overview(self):
        path = "/api/v1/operations/"
        self.assertEqual(self.client.get(path).status_code, 401)
        user = User.objects.create_user("customer")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(path).status_code, 403)
        user.is_staff = True
        user.save()
        self.assertEqual(self.client.get(path).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="access_operations_dashboard"))
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(path, {"status": "approved"}).status_code, 405)
