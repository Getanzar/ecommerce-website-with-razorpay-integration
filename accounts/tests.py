from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import SellerApplicationForm, SignUpForm
from .models import SellerProfile
from .utils import send_email_otp, send_password_reset_otp


class SignUpTests(TestCase):
    def setUp(self):
        self.existing = get_user_model().objects.create_user(
            username="existinguser", email="existing@example.com"
        )
        self.existing.profile.phone = "9876543210"
        self.existing.profile.save(update_fields=["phone"])
        self.data = {
            "first_name": "New",
            "last_name": "Customer",
            "username": "newcustomer",
            "email": "new@example.com",
            "phone": "9123456789",
            "password1": "A-strong-test-password-123",
            "password2": "A-strong-test-password-123",
            "terms": "on",
        }

    def test_any_duplicate_identifier_prevents_account_creation(self):
        cases = {
            "username": "ExistingUser",
            "email": "EXISTING@example.com",
            "phone": "9876543210",
        }
        for field, duplicate_value in cases.items():
            with self.subTest(field=field):
                data = {**self.data, field: duplicate_value}
                form = SignUpForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                with self.assertRaises(ValueError):
                    form.save()

    def test_duplicate_signup_post_does_not_create_any_user(self):
        original_count = get_user_model().objects.count()
        for field, duplicate_value in {
            "username": "ExistingUser",
            "email": "EXISTING@example.com",
            "phone": "9876543210",
        }.items():
            with self.subTest(field=field):
                response = self.client.post(reverse("signup"), {**self.data, field: duplicate_value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(get_user_model().objects.count(), original_count)

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_valid_signup_sends_otp_and_redirects_to_verification(self, send_email):
        response = self.client.post(reverse("signup"), self.data)
        self.assertRedirects(response, reverse("verify_otp"), fetch_redirect_response=False)
        self.assertTrue(get_user_model().objects.filter(username="newcustomer").exists())
        send_email.assert_called_once()

    @patch("accounts.views.send_email_otp", return_value=False)
    def test_failed_otp_delivery_does_not_create_account_or_redirect(self, _send_otp):
        with patch("accounts.views.render", return_value=HttpResponse("signup")):
            response = self.client.post(reverse("signup"), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="newcustomer").exists())
        self.assertNotIn("pending_verification_email", self.client.session)

    @patch(
        "accounts.utils.EmailOTP.objects.update_or_create",
        side_effect=RuntimeError("OTP storage unavailable"),
    )
    def test_otp_storage_failure_does_not_return_server_error(self, _store_otp):
        with patch("accounts.views.render", return_value=HttpResponse("signup")):
            response = self.client.post(reverse("signup"), self.data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="newcustomer").exists())


class SellerApplicationFormTests(TestCase):
    def test_every_application_detail_is_required(self):
        form = SellerApplicationForm()

        for field_name, field in form.fields.items():
            with self.subTest(field=field_name):
                self.assertTrue(field.required)
                self.assertTrue(field.widget.attrs["required"])
                self.assertEqual(field.widget.attrs["aria-required"], "true")

    def test_empty_application_is_rejected(self):
        form = SellerApplicationForm(data={})

        self.assertFalse(form.is_valid())
        self.assertEqual(set(form.errors), set(form.fields))


class SellerAIPlanTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("plan-seller")
        self.seller = SellerProfile.objects.create(user=user, store_name="Plan Store")

    def test_active_plan_reports_remaining_images(self):
        self.seller.ai_plan = "starter"
        self.seller.ai_image_limit = 25
        self.seller.ai_images_used = 4
        self.seller.ai_subscription_ends_at = timezone.now() + timedelta(days=30)

        self.assertTrue(self.seller.ai_subscription_active)
        self.assertEqual(self.seller.ai_images_remaining, 21)

    def test_expired_plan_has_no_access(self):
        self.seller.ai_plan = "pro"
        self.seller.ai_image_limit = 400
        self.seller.ai_subscription_ends_at = timezone.now() - timedelta(seconds=1)

        self.assertFalse(self.seller.ai_subscription_active)
        self.assertEqual(self.seller.ai_images_remaining, 0)


class OTPEmailBrandingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password",
        )

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_signup_otp_uses_brevo_transactional_api(self, send_email):
        self.assertTrue(send_email_otp(self.user))
        self.assertEqual(send_email.call_args.kwargs["to_email"], self.user.email)
        self.assertIn("html_content", send_email.call_args.kwargs)

    @patch("accounts.utils.send_transactional_email", return_value=True)
    def test_password_reset_otp_uses_brevo_transactional_api(self, send_email):
        self.assertTrue(send_password_reset_otp(self.user))
        self.assertEqual(send_email.call_args.kwargs["to_email"], self.user.email)
        self.assertIn("html_content", send_email.call_args.kwargs)
