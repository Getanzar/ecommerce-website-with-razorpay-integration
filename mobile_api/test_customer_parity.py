import base64
import hashlib
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import GoogleAccount, SellerProfile
from food.models import FoodDeliveryAreaRequest, FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant


class CustomerParityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("mobile-customer", email="buyer@example.com", password="Secure-buyer-429!")
        self.user.profile.email_verified = True
        self.user.profile.save()

    @patch("mobile_api.views.send_email_otp", return_value=True)
    def test_email_password_signup_generates_username_and_waits_for_verification(self, send):
        response = self.client.post(reverse("mobile-signup"), {"email": "NEW@example.com", "password": "Unique-Strong-934!"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="new@example.com")
        self.assertTrue(user.username.startswith("customer_"))
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.phone, "")
        self.assertTrue(user.check_password("Unique-Strong-934!"))
        self.assertNotIn("token", response.data)

    def test_profile_optional_fields_and_login_identifier_validation(self):
        self.client.force_authenticate(self.user)
        url = reverse("mobile-profile")
        result = self.client.patch(url, {"username": "my-new-name", "gender": "Other", "date_of_birth": "2001-02-03", "phone": "9876543210"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["date_of_birth"], "2001-02-03")
        self.assertEqual(result.data["username"], "my-new-name")
        other = User.objects.create_user("someone-else", email="else@example.com")
        self.assertEqual(self.client.patch(url, {"username": other.username.upper()}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"phone": "123"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"gender": "invalid"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"date_of_birth": "bad"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"date_of_birth": "2999-01-01"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"date_of_birth": "", "phone": ""}, format="multipart").status_code, 200)

    def test_email_cannot_be_changed_without_otp(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(reverse("mobile-profile"), {"email": "unverified@example.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "buyer@example.com")

    @patch("mobile_api.customer_parity.send_profile_email_otp", return_value=True)
    def test_new_email_verified_once_and_old_email_retained_until_confirmation(self, send):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse("mobile-profile-email-request"), {"email": "newlogin@example.com"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        code = send.call_args.args[1]
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "buyer@example.com")
        verify = reverse("mobile-profile-email-verify")
        response = self.client.post(verify, {"otp": code}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["email"], "newlogin@example.com")
        self.assertEqual(self.client.post(verify, {"otp": code}, format="json").status_code, 400)

    @patch("mobile_api.customer_parity.send_profile_email_otp", return_value=True)
    def test_email_otp_has_attempt_limit_and_expiry(self, send):
        self.client.force_authenticate(self.user)
        self.client.post(reverse("mobile-profile-email-request"), {"email": "newlogin@example.com"}, format="json")
        code = send.call_args.args[1]
        for _ in range(5):
            self.assertEqual(self.client.post(reverse("mobile-profile-email-verify"), {"otp": "wrong"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(reverse("mobile-profile-email-verify"), {"otp": code}, format="json").status_code, 400)

    @patch("mobile_api.customer_parity.send_profile_email_otp", return_value=True)
    def test_expired_email_code_cannot_change_email(self, send):
        self.client.force_authenticate(self.user)
        self.client.post(reverse("mobile-profile-email-request"), {"email": "newlogin@example.com"}, format="json")
        key = f"mobile-email:{self.user.pk}"
        pending = cache.get(key)
        pending["expires"] = 0
        cache.set(key, pending, 600)
        response = self.client.post(reverse("mobile-profile-email-verify"), {"otp": send.call_args.args[1]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "buyer@example.com")

    def test_profile_photo_upload_and_invalid_file_rejection(self):
        import io
        import tempfile
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        photo = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(photo, format="PNG")
        self.client.force_authenticate(self.user)
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
            result = self.client.patch(reverse("mobile-profile"), {"profile_picture": SimpleUploadedFile("avatar.png", photo.getvalue(), content_type="image/png")}, format="multipart")
            self.assertEqual(result.status_code, 200, result.data)
            self.assertTrue(result.data["profile_picture_url"].startswith("http://testserver/media/profiles/"))
            self.assertNotIn("profile_picture", result.data)
            result = self.client.patch(reverse("mobile-profile"), {"profile_picture": SimpleUploadedFile("broken.png", b"not an image", content_type="image/png")}, format="multipart")
            self.assertEqual(result.status_code, 400)

    def test_small_seller_forms_for_every_segment_exclude_pan_and_gst_enrolment(self):
        self.client.force_authenticate(self.user)
        for segment in ("shop", "food", "grocery"):
            response = self.client.get(f"/api/v1/partners/applications/seller/?registration_type=small&business_segment={segment}")
            self.assertEqual(response.status_code, 200, response.data)
            fields = {field["name"] for field in response.data["fields"]}
            self.assertNotIn("pan_number", fields)
            self.assertNotIn("gst_enrolment_number", fields)
            self.assertNotIn("gstin", fields)
            self.assertFalse(any("pan" == name or name.startswith("pan_") or name.startswith("gst") for name in fields))
            self.assertIn("store_name", fields)

    def test_delivery_interest_is_validated_saved_and_rate_limited(self):
        url = reverse("mobile-delivery-interest")
        self.assertEqual(self.client.post(url, {"pincode": "123", "comment": "hello"}, format="json").status_code, 400)
        self.client.force_authenticate(self.user)
        response = self.client.post(url, {"pincode": "110001", "comment": "Bring local food here"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        row = FoodDeliveryAreaRequest.objects.get()
        self.assertEqual(row.user, self.user)
        self.assertEqual(row.comment, "Bring local food here")
        self.assertEqual(self.client.post(url, {"pincode": "110001"}, format="json").status_code, 429)
        self.assertEqual(FoodDeliveryAreaRequest.objects.count(), 1)

    def test_grocery_interest_is_identifiable_in_admin(self):
        result = self.client.post(reverse("mobile-delivery-interest"), {"pincode": "110001", "service": "grocery"}, format="json")
        self.assertEqual(result.status_code, 201)
        self.assertEqual(FoodDeliveryAreaRequest.objects.get().service, "grocery")


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client", GOOGLE_OAUTH_CLIENT_SECRET="test-secret", GOOGLE_OAUTH_REDIRECT_URI="http://testserver/accounts/google/callback/")
class GoogleMobileTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.verifier = "v" * 64
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()

    def start(self, token_user=None):
        if token_user:
            self.client.force_authenticate(token_user)
        result = self.client.post(reverse("mobile-google-start"), {"challenge": self.challenge, "state": "s" * 64}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        browser = Client()
        response = browser.get(result.data["url"])
        self.assertEqual(response.status_code, 302)
        return browser, browser.session["google_oauth"], result.data["url"]

    def test_google_flow_verifies_provider_and_returns_single_use_pkce_code(self):
        browser, flow, url = self.start()
        self.assertEqual(browser.get(url).status_code, 400)
        claims = {"sub": "mobile-google-123", "email": "google@example.com", "email_verified": True, "nonce": flow["nonce"]}
        with patch("accounts.google_auth.requests.post") as post, patch("accounts.google_auth.verify_oauth2_token", return_value=claims):
            post.return_value.json.return_value = {"id_token": "signed-provider-token"}
            result = browser.get(reverse("google_callback"), {"state": flow["state"], "code": "provider-code"})
        self.assertEqual(result.status_code, 302)
        self.assertTrue(result.url.startswith("ziyamart://auth/callback?"))
        params = parse_qs(urlparse(result.url).query)
        self.assertNotIn("token", params)
        self.assertEqual(params["state"], ["s" * 64])
        exchange = reverse("mobile-google-exchange")
        code = params["code"][0]
        self.assertEqual(self.client.post(exchange, {"code": code, "verifier": "x" * 64}, format="json").status_code, 400)
        response = self.client.post(exchange, {"code": code, "verifier": self.verifier}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["email"], "google@example.com")
        self.assertTrue(response.data["token"])
        self.assertEqual(self.client.post(exchange, {"code": code, "verifier": self.verifier}, format="json").status_code, 400)
        self.assertEqual(GoogleAccount.objects.count(), 1)

    def test_existing_email_requires_explicit_linking_from_authenticated_app(self):
        user = User.objects.create_user("existing", email="google@example.com")
        user.profile.email_verified = True
        user.profile.save()
        browser, flow, _ = self.start()
        with patch("accounts.google_auth.requests.post") as post, patch("accounts.google_auth.verify_oauth2_token", return_value={"sub": "google-existing", "email": user.email, "email_verified": True, "nonce": flow["nonce"]}):
            post.return_value.json.return_value = {"id_token": "token"}
            result = browser.get(reverse("google_callback"), {"state": flow["state"], "code": "code"})
        self.assertIn("error=", result.url)
        self.assertFalse(GoogleAccount.objects.exists())
        cache.clear()
        browser, flow, _ = self.start(user)
        with patch("accounts.google_auth.requests.post") as post, patch("accounts.google_auth.verify_oauth2_token", return_value={"sub": "google-existing", "email": user.email, "email_verified": True, "nonce": flow["nonce"]}):
            post.return_value.json.return_value = {"id_token": "token"}
            result = browser.get(reverse("google_callback"), {"state": flow["state"], "code": "code"})
        self.assertIn("code=", result.url)
        self.assertEqual(GoogleAccount.objects.get().user, user)
        code = parse_qs(urlparse(result.url).query)["code"][0]
        with patch("mobile_api.views.auth_payload") as issue:
            response = self.client.post(reverse("mobile-google-exchange"), {"code": code, "verifier": self.verifier}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["linked"])
        self.assertNotIn("token", response.data)
        issue.assert_not_called()

    def test_google_cancel_returns_to_app_without_account_creation(self):
        browser, flow, _ = self.start()
        result = browser.get(reverse("google_callback"), {"state": flow["state"], "error": "access_denied"})
        self.assertTrue(result.url.startswith("ziyamart://auth/callback?"))
        self.assertIn("error=", result.url)
        self.assertFalse(GoogleAccount.objects.exists())


class FoodDiscoveryTests(APITestCase):
    def setUp(self):
        cache.clear()
        area = FoodServiceArea.objects.create(pincode="110001")
        for index, (name, dish, food_type, minutes) in enumerate((("Local Kitchen", "Paneer curry", "veg", 10), ("Birya House", "Chicken biryani", "non_veg", 30))):
            user = User.objects.create_user(f"cook-{index}")
            seller = SellerProfile.objects.create(user=user, store_name=name, business_segment="food", status="approved")
            restaurant = Restaurant.objects.create(seller=seller, name=name, slug=f"kitchen-{index}", cuisine="Indian", pincode="110001", preparation_minutes=minutes)
            restaurant.service_areas.add(area)
            section = MenuSection.objects.create(restaurant=restaurant, name="Main course")
            item = MenuItem.objects.create(restaurant=restaurant, section=section, name=dish, food_type=food_type)
            MenuItemOption.objects.create(item=item, name="Regular", price=100)

    def test_restaurant_search_filters_dishes_veg_cuisine_and_pincode(self):
        url = reverse("mobile-restaurants")
        result = self.client.get(url, {"q": "paneer", "pincode": "110001"})
        self.assertEqual([row["name"] for row in result.data], ["Local Kitchen"])
        self.assertEqual(len(self.client.get(url, {"veg": "true"}).data), 1)
        self.assertEqual(len(self.client.get(url, {"cuisine": "Biryani"}).data), 1)
        self.assertEqual(self.client.get(url, {"pincode": "110002"}).data, [])
        self.assertEqual(self.client.get(url, {"sort": "fastest"}).data[0]["name"], "Local Kitchen")
        self.assertEqual(self.client.get(url, {"sort": "newest"}).data[0]["name"], "Birya House")

    def test_menu_hides_unavailable_dishes_and_options(self):
        item = MenuItem.objects.get(name="Paneer curry")
        hidden = MenuItemOption.objects.create(item=item, name="Hidden", price=150, is_available=False)
        url = reverse("mobile-restaurant-detail", kwargs={"slug": item.restaurant.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(hidden.pk, [option["id"] for option in response.data["menu_items"][0]["options"]])
        item.is_available = False
        item.save()
        self.assertEqual(self.client.get(url).data["menu_items"], [])
