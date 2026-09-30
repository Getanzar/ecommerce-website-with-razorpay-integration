from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import EmailOTP
from mobile_api.models import DeviceSession


class AuthSafetyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def post(self, name, data, **extra):
        return self.client.post(reverse(name), data, format="json", **extra)

    def pending(self, verified=False):
        user = User.objects.create_user("pending", email="pending@example.com", password="Original-Strong-72!", is_active=False)
        user.profile.email_verified = verified
        user.profile.save()
        EmailOTP.objects.create(user=user, otp="123456", expires_at=timezone.now() - timedelta(minutes=1))
        return user

    @patch("accounts.utils._send_otp_email", return_value=True)
    def test_expired_signup_can_resend_and_verify_without_changing_credentials(self, send):
        user = self.pending()
        password_hash = user.password
        response = self.post("mobile-resend-otp", {"email": " PENDING@example.com "})
        self.assertEqual(response.status_code, 200)
        otp = EmailOTP.objects.get(user=user)
        self.assertFalse(otp.is_expired())
        self.assertEqual(otp.attempts, 0)
        response = self.post("mobile-verify-otp", {"email": user.email, "otp": otp.otp})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.email_verified)
        self.assertEqual(user.password, password_hash)
        self.assertEqual(DeviceSession.objects.filter(user=user).count(), 1)
        self.assertFalse(EmailOTP.objects.filter(user=user).exists())

    @patch("accounts.utils._send_otp_email", return_value=True)
    def test_resend_is_generic_and_never_reactivates_verified_disabled_user(self, send):
        user = self.pending(verified=True)
        disabled = self.post("mobile-resend-otp", {"email": user.email})
        unknown = self.post("mobile-resend-otp", {"email": "unknown@example.com"})
        self.assertEqual(disabled.data["message"], unknown.data["message"])
        self.assertEqual(disabled.status_code, unknown.status_code)
        send.assert_not_called()
        otp = EmailOTP.objects.get(user=user)
        otp.expires_at = timezone.now() + timedelta(minutes=5)
        otp.save()
        response = self.post("mobile-verify-otp", {"email": user.email, "otp": otp.otp})
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    @patch("accounts.utils._send_otp_email", return_value=False)
    def test_failed_resend_preserves_previous_code(self, send):
        user = self.pending()
        old = EmailOTP.objects.get(user=user)
        response = self.post("mobile-resend-otp", {"email": user.email})
        self.assertEqual(response.status_code, 200)
        current = EmailOTP.objects.get(user=user)
        self.assertEqual(current.otp, old.otp)
        self.assertEqual(current.expires_at, old.expires_at)

    @patch("mobile_api.views.send_email_otp", return_value=False)
    def test_failed_signup_rolls_back_new_account(self, send):
        response = self.post("mobile-signup", {"username": "newbuyer", "email": "new@example.com", "phone": "9876543210", "password": "Strong-Secret-72!"})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(User.objects.filter(username="newbuyer").exists())

    @patch("mobile_api.views.send_email_otp")
    def test_signup_rejects_weak_passwords_and_malformed_identity(self, send):
        for changes in ({"password": "12345678"}, {"password": "password"}, {"password": "newbuyer"}, {"email": "bad@"}, {"username": "x" * 151}):
            cache.clear()
            payload = {"username": "newbuyer", "email": "new@example.com", "phone": "9876543210", "password": "Strong-Secret-72!", **changes}
            response = self.post("mobile-signup", payload)
            self.assertEqual(response.status_code, 400, response.data)
        send.assert_not_called()
        self.assertFalse(User.objects.exists())

    @patch("accounts.utils._send_otp_email", return_value=True)
    def test_resend_cooldown_is_shared_across_ip_addresses(self, send):
        user = self.pending()
        first = self.post("mobile-resend-otp", {"email": user.email}, REMOTE_ADDR="192.0.2.1")
        second = self.post("mobile-resend-otp", {"email": user.email.upper()}, REMOTE_ADDR="192.0.2.2")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertGreater(int(second["Retry-After"]), 0)
        send.assert_called_once()

    @patch("accounts.utils._send_otp_email", return_value=True)
    def test_signup_and_resend_share_cooldown(self, send):
        response = self.post("mobile-signup", {"username": "newbuyer", "email": "new@example.com", "phone": "9876543210", "password": "Strong-Secret-72!"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.post("mobile-resend-otp", {"email": "new@example.com"}).status_code, 429)
        send.assert_called_once()

    def test_login_aliases_share_limit_and_other_account_can_login(self):
        user = User.objects.create_user("buyer", email="buyer@example.com", password="Strong-Secret-72!")
        for index in range(10):
            response = self.post("mobile-login", {"identity": user.username if index % 2 else user.email.upper(), "password": "wrong"}, REMOTE_ADDR=f"192.0.2.{index + 1}")
            self.assertEqual(response.status_code, 400)
        response = self.post("mobile-login", {"identity": user.email, "password": "Strong-Secret-72!"}, REMOTE_ADDR="192.0.2.20")
        self.assertEqual(response.status_code, 429)
        other = User.objects.create_user("other", email="other@example.com", password="Strong-Secret-72!")
        self.assertEqual(self.post("mobile-login", {"identity": other.email, "password": "Strong-Secret-72!"}).status_code, 200)

    def test_login_ip_limit_cannot_be_evaded_by_spoofing_forwarded_headers(self):
        for index in range(30):
            response = self.post("mobile-login", {"identity": f"missing{index}", "password": "wrong"}, HTTP_X_FORWARDED_FOR=f"192.0.2.{index}")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("mobile-login", {"identity": "another", "password": "wrong"}, HTTP_X_FORWARDED_FOR="198.51.100.1").status_code, 429)

    def test_otp_attempt_limit_and_replay(self):
        user = self.pending()
        otp = EmailOTP.objects.get(user=user)
        otp.expires_at = timezone.now() + timedelta(minutes=5)
        otp.save()
        for _ in range(5):
            self.assertEqual(self.post("mobile-verify-otp", {"email": user.email, "otp": "000000"}).status_code, 400)
        self.assertEqual(self.post("mobile-verify-otp", {"email": user.email, "otp": otp.otp}).status_code, 400)
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 5)
        self.assertFalse(DeviceSession.objects.exists())

    @patch("mobile_api.views.send_password_reset_otp", side_effect=RuntimeError("provider unavailable"))
    def test_reset_provider_failure_does_not_expose_account(self, send):
        User.objects.create_user("buyer", email="buyer@example.com")
        known = self.post("mobile-password-reset-request", {"email": "buyer@example.com"})
        unknown = self.post("mobile-password-reset-request", {"email": "unknown@example.com"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)

    def test_non_object_auth_payload_is_rejected(self):
        self.assertEqual(self.post("mobile-login", ["bad"]).status_code, 400)

    def test_shared_cache_deployment_check(self):
        from mobile_api.checks import shared_auth_cache
        self.assertEqual(shared_auth_cache(None)[0].id, "mobile_api.W001")
        with override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "test_cache"}}):
            self.assertEqual(shared_auth_cache(None), [])
