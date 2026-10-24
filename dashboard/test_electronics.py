from django.test import TestCase
from django.template.loader import get_template
from django.urls import reverse
from products.models import Product, Category
from dashboard.electronics import ElectronicsProductForm
from products.electronics import ELECTRONICS

class ElectronicsTests(TestCase):
    def test_customer_browse_and_empty_categories(self):
        for kind in [""] + list(ELECTRONICS):
            response = self.client.get(reverse("electronics_page"), {"type": kind})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "New tech is on its way")
        self.assertContains(self.client.get(reverse("categories_page")), "Electronics")

    def test_templates_compile(self):
        for name in ("products/electronics.html", "dashboard/seller/electronics_product.html", "dashboard/seller/dashboard.html", "dashboard/seller/add_product.html"):
            get_template(name)

    def test_only_relevant_specs(self):
        mobile = ElectronicsProductForm(kind="mobile")
        tv = ElectronicsProductForm(kind="tv")
        self.assertIn("spec_ram", mobile.fields)
        self.assertNotIn("spec_ram", tv.fields)
        self.assertIn("spec_resolution", tv.fields)
        self.assertNotIn("gender", mobile.fields)

    def test_required_specs_and_positive_price(self):
        form = ElectronicsProductForm({"name": "Phone", "price": "-1", "quantity": "-1"}, kind="mobile")
        self.assertFalse(form.is_valid())
        for key in ("price", "quantity", "spec_ram", "brand", "warranty"):
            self.assertIn(key, form.errors)

    def test_existing_mobile_product_reuses_its_specs(self):
        product = Product.objects.create(category=Category.objects.get(slug="electronics"), name="Existing phone", price=100, product_type="mobile", specifications={"brand": "Test", "RAM": "8 GB"})
        form = ElectronicsProductForm(instance=product, kind="mobile")
        self.assertEqual(form.fields["brand"].initial, "Test")
        self.assertEqual(form.fields["spec_ram"].initial, "8 GB")

    def test_existing_seller_can_submit_mobile_for_review(self):
        from django.contrib.auth import get_user_model
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from accounts.models import SellerProfile
        from PIL import Image
        from io import BytesIO
        user = get_user_model().objects.create_user("electronics-seller")
        seller = SellerProfile.objects.create(user=user, store_name="Mobile store", business_segment="shop", status="approved")
        self.client.force_login(user)
        for kind in ELECTRONICS:
            self.assertEqual(self.client.get(reverse("seller_add_electronics", args=[kind])).status_code, 200)
        data = {"name": "Test phone", "description": "New boxed phone", "price": "20000", "gst_rate": "18", "brand": "Test", "model_number": "M1", "warranty": "1 year", "color": "Black", "quantity": 4, "package_weight_grams": 500, "package_length_cm": 20, "package_width_cm": 15, "package_height_cm": 8}
        for label in ELECTRONICS["mobile"]["fields"]:
            data["spec_" + label.lower().replace(" ", "_")] = "Test specification"
        picture = BytesIO()
        Image.new("RGB", (10, 10)).save(picture, "PNG")
        data["image"] = SimpleUploadedFile("phone.png", picture.getvalue(), content_type="image/png")
        with override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
            response = self.client.post(reverse("seller_add_electronics", args=["mobile"]), data)
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(seller=seller)
        self.assertFalse(product.is_active)
        self.assertEqual(product.moderation_status, "pending")
        self.assertEqual(product.variants.get().stock, 4)
        self.assertEqual(product.specifications["brand"], "Test")
        self.assertNotContains(self.client.get(reverse("electronics_page")), "Test phone")
