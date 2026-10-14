from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

class MobileSignupRecoveryTests(APITestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        self.user = User.objects.create_user("ExistingUser", email="existing@example.com")
        self.user.profile.phone="9876543210"; self.user.profile.save()
        self.payload = {"username":"newbuyer", "email":"new@example.com", "phone":"9123456789", "password":"Strong-New-Secret-72!"}

    @patch("mobile_api.views.send_email_otp")
    def test_duplicates_offer_recovery_without_creating_account(self, send):
        for field, value in {"username":"existinguser", "email":" EXISTING@example.com ", "phone":"+91 98765-43210"}.items():
            cache.clear()
            response = self.client.post(reverse("mobile-signup"), {**self.payload, field:value}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertTrue(response.data["account_exists"])
            self.assertIn("username", response.data["recovery"])
            self.assertEqual(User.objects.count(), 1)
        send.assert_not_called()

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_username_reminder_does_not_reveal_user_in_api_response(self, send):
        response = self.client.post(reverse("mobile-username-recovery"), {"email":self.user.email}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(self.user.username, str(response.data))
        send.assert_called_once()
        unknown = self.client.post(reverse("mobile-username-recovery"), {"email":"unknown@example.com"}, format="json")
        self.assertEqual(response.data, unknown.data)
