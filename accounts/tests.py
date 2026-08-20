from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .forms import SellerApplicationForm
from .models import SellerProfile
from .utils import send_email_otp, send_password_reset_otp


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


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="ulhaqanzar444@gmail.com",
)
class OTPEmailBrandingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password",
        )

    def test_signup_otp_uses_ziyamart_sender_name(self):
        self.assertTrue(send_email_otp(self.user))

        self.assertEqual(mail.outbox[0].from_email, "ZIYAMART <ulhaqanzar444@gmail.com>")

    def test_password_reset_otp_uses_ziyamart_sender_name(self):
        self.assertTrue(send_password_reset_otp(self.user))

        self.assertEqual(mail.outbox[0].from_email, "ZIYAMART <ulhaqanzar444@gmail.com>")
