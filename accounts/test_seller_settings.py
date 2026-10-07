import io
import tempfile
from datetime import timedelta

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import SellerProfile
from food.models import Restaurant
from groceries.models import GroceryStore


class SellerSettingsTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name,
            STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                      "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = User.objects.create_user("settings-seller")
        self.seller = SellerProfile.objects.create(user=self.user, store_name="Original store",
            business_segment="grocery", status="approved", business_phone="9876543210",
            business_pincode="110001", business_address="Original pickup")
        self.other = SellerProfile.objects.create(user=User.objects.create_user("other-settings-seller"),
            store_name="Other store", business_segment="grocery", status="approved")
        self.store = GroceryStore.objects.create(seller=self.seller, name="Public grocery",
            address="Original pickup", phone="9876543210", pincode="110001")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.url = "/api/v1/partners/seller/profile/"
        self.client.force_login(self.user)

    def payload(self, **changes):
        return {"store_name": "Updated business", "description": "Fresh local essentials",
                "business_phone": "9876543211", "business_address": "Updated pickup",
                "business_pincode": "110002", "business_latitude": "28.610000",
                "business_longitude": "77.210000", "business_gps_accuracy_meters": "15",
                "gps_captured_at": timezone.now().isoformat(), **changes}

    def photo(self, name="logo.png"):
        output = io.BytesIO()
        Image.new("RGB", (12, 12), "red").save(output, format="PNG")
        return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")

    def test_mobile_save_updates_web_profile_and_delivery_location(self):
        response = self.api.post(self.url, self.payload(logo=self.photo(), cover_image=self.photo("cover.png")), format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.seller.refresh_from_db(); self.store.refresh_from_db()
        self.assertEqual(self.store.pincode, "110002")
        self.assertEqual(self.store.address, "Updated pickup")
        self.assertEqual(self.store.phone, "9876543211")
        self.assertTrue(self.seller.logo)
        response = self.client.get(reverse("seller_profile_settings"))
        self.assertContains(response, "Updated business")
        self.assertContains(response, self.seller.logo.url)
        workspace = self.api.get("/api/v1/partners/seller/")
        self.assertEqual(workspace.status_code, 200, workspace.data)
        self.assertEqual(workspace.data["pincode"], "110002")
        self.assertTrue(workspace.data["logo_url"].startswith("http"))

    def test_web_save_visible_in_mobile_schema_with_photo_retention_and_clear(self):
        response = self.client.post(reverse("seller_profile_settings"), self.payload(logo=self.photo()))
        self.assertEqual(response.status_code, 302)
        schema = self.api.get(self.url).data
        fields = {field["name"]: field for field in schema["fields"]}
        self.assertEqual(fields["store_name"]["value"], "Updated business")
        self.assertTrue(fields["logo"]["preview_url"])
        self.seller.refresh_from_db(); original = self.seller.logo.name
        self.assertEqual(self.api.post(self.url, self.payload(), format="multipart").status_code, 200)
        self.seller.refresh_from_db(); self.assertEqual(self.seller.logo.name, original)
        self.assertEqual(self.api.post(self.url, self.payload(**{"logo-clear": "on"}), format="multipart").status_code, 200)
        self.seller.refresh_from_db(); self.assertFalse(self.seller.logo)

    def test_profile_ignores_privileged_fields_and_other_seller_id(self):
        response = self.api.post(self.url, self.payload(seller_id=self.other.pk, status="rejected",
            business_segment="food", payouts_enabled="True", commission_rate="0"), format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.seller.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.seller.status, "approved")
        self.assertEqual(self.seller.business_segment, "grocery")
        self.assertFalse(self.seller.payouts_enabled)
        self.assertEqual(self.other.store_name, "Other store")
        self.assertEqual(self.api.get("/api/v1/partners/seller/food/store/").status_code, 403)

    def test_invalid_pincode_and_stale_gps_do_not_save(self):
        for changes in [{"business_pincode": "abc"}, {"gps_captured_at": (timezone.now()-timedelta(minutes=10)).isoformat()}]:
            response = self.api.post(self.url, self.payload(**changes), format="multipart")
            self.assertEqual(response.status_code, 400, response.data)
        self.seller.refresh_from_db(); self.assertEqual(self.seller.store_name, "Original store")

    def test_pending_seller_cannot_update_profile(self):
        self.seller.status = "pending"; self.seller.save()
        self.assertEqual(self.api.post(self.url, self.payload(), format="multipart").status_code, 403)
        self.assertEqual(self.client.get(reverse("seller_profile_settings")).status_code, 403)

    def test_settings_render_for_each_segment_and_store_preview(self):
        for segment in ["shop", "food", "grocery"]:
            self.seller.business_segment = segment; self.seller.save()
            response = self.client.get(reverse("seller_profile_settings"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Save changes")
        self.store.image = self.photo("store.png"); self.store.save()
        response = self.api.get("/api/v1/partners/seller/grocery/store/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(next(f for f in response.data["fields"] if f["name"] == "image")["preview_url"])
        self.assertContains(self.client.get(reverse("grocery_seller_setup")), "Current store photo")
        self.seller.business_segment = "food"; self.seller.save()
        Restaurant.objects.create(seller=self.seller, name="Kitchen", pincode="110001")
        self.assertContains(self.client.get(reverse("food_seller_setup")), "Save changes")

    def test_food_profile_location_sync(self):
        self.seller.business_segment = "food"; self.seller.save()
        restaurant = Restaurant.objects.create(seller=self.seller, name="Kitchen", pincode="110001")
        response = self.api.post(self.url, self.payload(), format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        restaurant.refresh_from_db(); self.assertEqual(restaurant.pincode, "110002")

    def test_store_edits_sync_profile_and_existing_public_photo(self):
        from groceries.models import GroceryServiceArea
        area = GroceryServiceArea.objects.create(pincode="110003")
        payload = {"name": "Fresh Market", "description": "Daily groceries", "address": "New market pickup",
                   "phone": "9876543212", "pincode": "110003", "latitude": "28.61",
                   "longitude": "77.21", "gps_accuracy_meters": "12", "gps_captured_at": timezone.now().isoformat(),
                   "minimum_order": "100", "delivery_fee": "20", "estimated_delivery_minutes": "30",
                   "service_areas": [str(area.pk)], "image": self.photo("new-store.png")}
        response = self.api.post("/api/v1/partners/seller/grocery/store/", payload, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.seller.refresh_from_db(); self.store.refresh_from_db()
        self.assertEqual(self.seller.business_pincode, "110003")
        self.assertEqual(self.seller.business_address, "New market pickup")
        self.assertTrue(self.store.image)
        self.assertContains(self.client.get(reverse("grocery_seller_setup")), "Fresh Market")
        payload.pop("image"); payload["name"] = "Fresh Market Updated"
        response = self.client.post(reverse("grocery_seller_setup"), payload)
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db(); self.assertTrue(self.store.image)
        fields = self.api.get("/api/v1/partners/seller/grocery/store/").data["fields"]
        self.assertEqual(next(f for f in fields if f["name"] == "name")["value"], "Fresh Market Updated")
