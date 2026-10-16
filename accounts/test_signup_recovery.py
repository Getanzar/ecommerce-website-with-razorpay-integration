from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from .forms import SignUpForm, CustomerProfileForm
from .models import UserProfile

class SignupRecoveryTests(TestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        self.existing = User.objects.create_user("ExistingUser", email="existing@example.com", password="Original-Secret-72!")
        self.existing.profile.phone = "9876543210"; self.existing.profile.save()
        self.payload = {"first_name": "Existing", "last_name": "User", "username": "newbuyer", "email": "new@example.com", "phone": "9123456789", "password1": "Strong-New-Secret-72!", "password2": "Strong-New-Secret-72!", "terms": "on"}

    @patch("accounts.views.send_email_otp")
    def test_each_duplicate_returns_recovery_links_without_creating_account(self, send):
        for field, value in {"email": " EXISTING@example.com "}.items():
            response = self.client.post(reverse("signup"), {**self.payload, field: value})
            self.assertEqual(response.status_code, 200)
            for route in ("login", "forgot_username", "password_reset"):
                self.assertContains(response, reverse(route))
            self.assertContains(response, "No new account was created")
            self.assertEqual(User.objects.count(), 1)
        send.assert_not_called()
        self.assertNotIn("pending_verification_email", self.client.session)

    def test_database_rejects_email_and_username_case_variations(self):
        for changes in ({"username": "newbuyer", "email": " EXISTING@example.com "}, {"username": "existinguser", "email": "fresh@example.com"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.create_user(**changes)
        self.assertEqual(User.objects.count(), 1)

    def test_database_rejects_formatted_phone_duplicate(self):
        other = User.objects.create_user("newbuyer")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.filter(user=other).update(phone="+91 98765-43210")
        other.profile.refresh_from_db()
        self.assertEqual(other.profile.phone, "")

    def test_legacy_formatted_phone_is_detected(self):
        UserProfile.objects.filter(user=self.existing).update(phone="+91 98765-43210")
        other = User.objects.create_user("profile-buyer", email="profile@example.com")
        form = CustomerProfileForm({"username": other.username, "email": other.email, "phone": "9876543210"}, user=other)
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_same_personal_names_do_not_block_different_people(self):
        self.assertTrue(SignUpForm(self.payload).is_valid())

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_username_is_sent_to_registered_email_and_never_shown_in_response(self, send):
        response = self.client.post(reverse("forgot_username"), {"email": " EXISTING@example.com "})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.existing.username)
        self.assertEqual(send.call_args.kwargs["to_email"], self.existing.email)
        self.assertIn(self.existing.username, send.call_args.kwargs["html_content"])
        self.assertIn(reverse("password_reset"), response.content.decode())
        self.client.post(reverse("forgot_username"), {"email": self.existing.email})
        send.assert_called_once()

    @patch("accounts.utils.send_transactional_email")
    def test_unknown_and_disabled_accounts_have_identical_response_and_no_mail(self, send):
        self.existing.is_active = False; self.existing.save()
        unknown = self.client.post(reverse("forgot_username"), {"email": "unknown@example.com"})
        disabled = self.client.post(reverse("forgot_username"), {"email": self.existing.email})
        self.assertEqual(unknown.context["sent"], disabled.context["sent"])
        send.assert_not_called()

    def test_profile_update_cannot_take_other_account_identifiers(self):
        other = User.objects.create_user("other", email="other@example.com")
        self.client.force_login(other)
        response = self.client.post(reverse("profile_detail"), {"username": "other", "email": "EXISTING@example.com", "phone": "9123456789"})
        self.assertEqual(response.status_code, 200)
        other.refresh_from_db(); self.assertEqual(other.email, "other@example.com")
