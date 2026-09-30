import json
import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from products.models import Category, Product, ProductColor, ProductImage, ProductVariant


class MerchandiseUploadTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("upload-seller")
        self.seller = SellerProfile.objects.create(user=self.user, store_name="Upload garments", business_segment="shop", business_category="Clothing", status="approved")
        self.category = Category.objects.create(name="Clothing", slug="upload-clothing")
        self.client.force_authenticate(self.user)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.storage = override_settings(MEDIA_ROOT=self.media.name, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
        self.storage.enable()
        self.addCleanup(self.storage.disable)
        self.path = "/api/v1/partners/seller/products/new/"

    def photo(self, name):
        data = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(data, format="JPEG")
        return SimpleUploadedFile(name, data.getvalue(), content_type="image/jpeg")

    def payload(self, variants=None):
        data = {
            "category": str(self.category.pk), "name": "Blue cotton shirt", "description": "Cotton shirt with multiple sizes",
            "price": "250", "gst_rate": "5", "package_weight_grams": "500", "package_length_cm": "20",
            "package_width_cm": "15", "package_height_cm": "5", "product_type": "regular",
            "image": self.photo("front.jpg"), "back_image": self.photo("back.jpg"),
        }
        data["product_type"] = Product._meta.get_field("product_type").choices[0][0]
        if variants is not None:
            data["variants"] = json.dumps(variants)
        else:
            data.update(color_name="Blue", size="M", opening_stock="7")
        return data

    def test_upload_saves_photos_colors_and_sizes_pending_review(self):
        data = self.payload([{"color": "Blue", "size": "M", "stock": 5}, {"color": "blue", "size": "L", "stock": 8}, {"color": "Red", "size": "M", "stock": 3}])
        response = self.client.post(self.path, data, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(pk=response.data["id"])
        self.assertEqual(product.seller, self.seller)
        self.assertEqual(product.moderation_status, Product.MODERATION_PENDING)
        self.assertFalse(product.is_active)
        self.assertTrue(product.image.storage.exists(product.image.name))
        back = ProductImage.objects.get(product=product)
        self.assertTrue(back.image.storage.exists(back.image.name))
        self.assertEqual(ProductColor.objects.filter(product=product).count(), 2)
        self.assertEqual(list(product.variants.order_by("pk").values_list("color__name", "size", "stock")), [("Blue", "M", 5), ("Blue", "L", 8), ("Red", "M", 3)])

    def test_old_single_variant_client_still_uploads(self):
        response = self.client.post(self.path, self.payload(), format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        variant = ProductVariant.objects.get(product_id=response.data["id"])
        self.assertEqual((variant.color.name, variant.size, variant.stock), ("Blue", "M", 7))

    def test_invalid_variant_batches_never_create_partial_product(self):
        for variants in ([], [{"color": "Blue", "size": "M", "stock": -1}], [{"color": "", "size": "M", "stock": 1}],
                         [{"color": "Blue", "size": "M", "stock": 1}, {"color": " blue ", "size": "m", "stock": 2}]):
            with self.subTest(variants=variants):
                response = self.client.post(self.path, self.payload(variants), format="multipart")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("variants", response.data)
                self.assertEqual(Product.objects.count(), 0)
                self.assertEqual(ProductColor.objects.count(), 0)

    def test_missing_and_invalid_images_have_validation_errors(self):
        data = self.payload()
        del data["image"]
        response = self.client.post(self.path, data, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)
        data = self.payload()
        data["back_image"] = SimpleUploadedFile("bad.jpg", b"not a photo", content_type="image/jpeg")
        response = self.client.post(self.path, data, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("back_image", response.data)
        self.assertEqual(Product.objects.count(), 0)

    def test_other_segment_cannot_upload_merchandise(self):
        self.seller.business_segment = 'food'
        self.seller.business_category = "Food"; self.seller.save()
        response = self.client.post(self.path, self.payload(), format="multipart")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Product.objects.count(), 0)
