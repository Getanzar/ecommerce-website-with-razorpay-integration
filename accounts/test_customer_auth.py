import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import SignUpForm
from .models import EmailOTP, GoogleAccount


@override_settings(SECURE_SSL_REDIRECT=False)
class CustomerSignupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.payload = {"email": "new@example.com", "password1": "New-Account-Secret-429!"}

    def test_signup_has_only_email_and_password_and_ignores_extra_fields(self):
        form = SignUpForm({**self.payload, "username": "chosen", "phone": "9876543210", "first_name": "Injected", "is_staff": True})
        self.assertEqual(set(form.fields), {"email", "password1"})
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.username.startswith("customer_"))
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.profile.phone, "")
        self.assertEqual(user.first_name, "")

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_email_otp_verification_signs_in_and_goes_to_editable_profile(self, send):
        response = self.client.post(reverse("signup"), self.payload)
        self.assertRedirects(response, reverse("verify_otp"), fetch_redirect_response=False)
        user = User.objects.get(email=self.payload["email"])
        otp = EmailOTP.objects.get(user=user)
        response = self.client.post(reverse("verify_otp"), {"otp": otp.otp})
        self.assertRedirects(response, reverse("profile_detail"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.email_verified)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertFalse(EmailOTP.objects.filter(user=user).exists())
        self.assertNotIn("pending_verification_email", self.client.session)

    def test_email_and_legacy_username_login_and_disabled_account(self):
        user = User.objects.create_user("LegacyBuyer", email="buyer@example.com", password="Legacy-Secret-429!")
        for identity in ("LegacyBuyer", "legacybuyer", " BUYER@EXAMPLE.COM "):
            with self.subTest(identity=identity):
                self.assertEqual(authenticate(username=identity, password="Legacy-Secret-429!"), user)
                self.client.logout()
                response = self.client.post(reverse("login"), {"username": identity, "password": "Legacy-Secret-429!"})
                self.assertEqual(response.status_code, 302)
        user.is_active = False
        user.save()
        self.assertIsNone(authenticate(username="buyer@example.com", password="Legacy-Secret-429!"))

    def test_email_shaped_legacy_username_does_not_block_email_login(self):
        username_user = User.objects.create_user("buyer@example.com", email="legacy@example.com", password="Legacy-Secret-429!")
        email_user = User.objects.create_user("emailbuyer", email="buyer@example.com", password="New-Secret-429!")
        self.assertEqual(authenticate(username="buyer@example.com", password="Legacy-Secret-429!"), username_user)
        self.assertEqual(authenticate(username="buyer@example.com", password="New-Secret-429!"), email_user)
        # If the passwords happen to match, prefer the actual email identity.
        email_user.set_password("Legacy-Secret-429!")
        email_user.save()
        self.assertEqual(authenticate(username="buyer@example.com", password="Legacy-Secret-429!"), email_user)

    def test_existing_django_login_sessions_are_preserved(self):
        user = User.objects.create_user("legacy-session", email="legacy-session@example.com")
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.get(reverse("profile_detail")).status_code, 200)

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_incorrect_expired_and_locked_codes_cannot_activate_account(self, send):
        self.client.post(reverse("signup"), self.payload)
        user = User.objects.get(email=self.payload["email"])
        otp = user.email_otp
        otp.attempts = 5
        otp.save()
        self.client.post(reverse("verify_otp"), {"otp": otp.otp})
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        otp.attempts = 0
        otp.expires_at = timezone.now() - timedelta(seconds=1)
        otp.save()
        self.client.post(reverse("verify_otp"), {"otp": otp.otp})
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(EmailOTP.objects.filter(user=user).exists())
        self.client.post(reverse("resend_signup_otp"))
        otp.refresh_from_db()
        self.assertFalse(otp.is_expired())
        self.assertEqual(otp.attempts, 0)

    @patch("accounts.utils.send_profile_email_otp", return_value=True)
    def test_profile_details_are_optional_and_email_change_requires_otp(self, send):
        user = User.objects.create_user("profilebuyer", email="old@example.com")
        user.profile.email_verified = True
        user.profile.save()
        self.client.force_login(user)
        response = self.client.post(reverse("profile_detail"), {"username": user.username, "email": "new@example.com", "first_name": "New name", "phone": ""})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New name")
        self.assertEqual(user.email, "old@example.com")
        code = send.call_args.args[1]
        self.client.post(reverse("verify_profile_email"), {"otp": "wrong"})
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.client.post(reverse("verify_profile_email"), {"otp": code})
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.profile.email_verified)
        self.assertNotIn("pending_profile_email", self.client.session)

    def test_invalid_profile_fields_do_not_save_or_crash(self):
        user = User.objects.create_user("profilebuyer", email="old@example.com")
        self.client.force_login(user)
        response = self.client.post(reverse("profile_detail"), {"username": "", "email": "broken", "phone": "bad-phone", "date_of_birth": "not-a-date"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")


@override_settings(SECURE_SSL_REDIRECT=False, GOOGLE_OAUTH_CLIENT_ID="test-client.apps.googleusercontent.com", GOOGLE_OAUTH_CLIENT_SECRET="test-secret", GOOGLE_OAUTH_REDIRECT_URI="https://example.com/accounts/google/callback/")
class GoogleSigninTests(TestCase):
    def begin(self):
        response = self.client.post(reverse("google_start"))
        self.assertEqual(response.status_code, 302)
        self.flow = dict(self.client.session["google_oauth"])
        return response

    def claims(self, **changes):
        return {"sub": "google-user-123", "email": "google@example.com", "email_verified": True, "nonce": self.flow["nonce"], "given_name": "Google", **changes}

    def finish(self, claims=None):
        with patch("accounts.google_auth.requests.post") as post, patch("accounts.google_auth.verify_oauth2_token", return_value=claims if claims is not None else self.claims()):
            post.return_value.json.return_value = {"id_token": "verified-token"}
            response = self.client.get(reverse("google_callback"), {"state": self.flow["state"], "code": "one-use-code"})
        return response

    def test_google_start_has_state_nonce_pkce_and_requires_csrf(self):
        response = self.begin()
        params = parse_qs(urlparse(response.url).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["scope"], ["openid email profile"])
        self.assertIn("nonce", params)
        self.assertNotIn("test-secret", response.url)
        self.assertEqual(self.client.get(reverse("google_start")).status_code, 405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse("google_start")).status_code, 403)

    def test_new_google_customer_is_verified_passwordless_and_sent_to_profile(self):
        self.begin()
        response = self.finish()
        self.assertRedirects(response, reverse("profile_detail"))
        user = User.objects.get(email="google@example.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.email_verified)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.google_account.subject, "google-user-123")
        self.assertNotIn("google_oauth", self.client.session)
        # Replaying the callback must not authenticate a new session.
        self.client.logout()
        response = self.client.get(reverse("google_callback"), {"state": self.flow["state"], "code": "one-use-code"})
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.google_auth.requests.post")
    def test_invalid_and_expired_state_do_not_exchange_codes(self, post):
        self.begin()
        self.client.get(reverse("google_callback"), {"state": "wrong", "code": "code"})
        post.assert_not_called()
        self.begin()
        session = self.client.session
        session["google_oauth"] = {**self.flow, "started_at": 0}
        session.save()
        self.client.get(reverse("google_callback"), {"state": self.flow["state"], "code": "code"})
        post.assert_not_called()
        self.assertFalse(GoogleAccount.objects.exists())

    def test_wrong_nonce_unverified_email_and_wrong_authorized_party_are_rejected(self):
        for changes in ({"nonce": "wrong"}, {"email_verified": False}, {"azp": "another-client"}):
            with self.subTest(changes=changes):
                self.begin()
                self.finish(self.claims(**changes))
                self.assertFalse(User.objects.exists())
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_email_requires_explicit_linking_from_verified_profile(self):
        user = User.objects.create_user("existing-google", email="google@example.com", password="Existing-Secret-429!")
        user.profile.email_verified = True
        user.profile.save()
        self.begin()
        response = self.finish()
        self.assertRedirects(response, reverse("login"))
        self.assertFalse(GoogleAccount.objects.exists())
        self.client.force_login(user)
        self.begin()
        response = self.finish()
        self.assertRedirects(response, reverse("profile_detail"))
        self.assertEqual(GoogleAccount.objects.get().user, user)
        self.assertTrue(user.check_password("Existing-Secret-429!"))

    def test_google_subject_identifies_returning_user_even_after_email_change(self):
        user = User.objects.create_user("returning-google", email="new-primary@example.com")
        GoogleAccount.objects.create(user=user, subject="google-user-123")
        self.begin()
        response = self.finish()
        self.assertRedirects(response, reverse("profile_detail"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(User.objects.count(), 1)

    def test_disabled_google_customer_cannot_sign_in(self):
        user = User.objects.create_user("disabled-google", email="google@example.com", is_active=False)
        GoogleAccount.objects.create(user=user, subject="google-user-123")
        self.begin()
        self.finish()
        self.assertNotIn("_auth_user_id", self.client.session)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    @override_settings(GOOGLE_OAUTH_CLIENT_SECRET="")
    def test_missing_configuration_has_a_clear_fallback(self):
        response = self.client.post(reverse("google_start"), follow=True)
        self.assertContains(response, "Google sign-in is not available yet")
        self.assertNotIn("google_oauth", self.client.session)

    def test_google_signature_audience_and_expiry_are_actually_verified(self):
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        for audience, offset, valid_signature, succeeds in (("test-client.apps.googleusercontent.com", 300, True, True), ("wrong-client", 300, True, False), ("test-client.apps.googleusercontent.com", -300, True, False), ("test-client.apps.googleusercontent.com", 300, False, False)):
            self.client.logout()
            self.begin()
            now = int(timezone.now().timestamp())
            token = jwt.encode({**self.claims(), "iat": now - 600, "exp": now + offset, "aud": audience, "iss": "https://accounts.google.com"}, private_key, algorithm="RS256", headers={"kid": "test-key"})
            if not valid_signature:
                header, payload, signature = token.split(".")
                token = ".".join((header, payload, ("A" if signature[0] != "A" else "B") + signature[1:]))
            with patch("accounts.google_auth.requests.post") as post, patch("accounts.google_auth.GoogleRequest") as transport:
                post.return_value.json.return_value = {"id_token": token}
                transport.return_value.return_value = SimpleNamespace(status=200, data=json.dumps({"test-key": public_pem}).encode())
                self.client.get(reverse("google_callback"), {"state": self.flow["state"], "code": "code"})
            self.assertEqual("_auth_user_id" in self.client.session, succeeds)
