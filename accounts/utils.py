import secrets
import logging

from datetime import timedelta
from django.template.loader import render_to_string
from django.utils import timezone

from config.email import send_transactional_email
from .models import EmailOTP


logger = logging.getLogger(__name__)


def _send_otp_email(user, subject, template_name, context):
    html = render_to_string(template_name, context)
    return send_transactional_email(
        to_email=user.email,
        to_name=user.get_full_name(),
        subject=subject,
        html_content=html,
    )


def send_email_otp(user):
    try:
        otp = f"{secrets.randbelow(900000) + 100000:06d}"
        expires_at = timezone.now() + timedelta(minutes=5)

        EmailOTP.objects.update_or_create(
            user=user,
            defaults={
                "otp": otp,
                "expires_at": expires_at,
                "attempts": 0,
                "is_verified": False,
            },
        )

        return _send_otp_email(
            user,
            "Your ZIYAMART Verification Code",
            "emails/email_otp.html",
            {"user": user, "otp": otp},
        )
    except Exception:
        logger.exception("ZIYAMART OTP could not be prepared for user %s", user.pk)
        return False


def send_password_reset_otp(user):
    otp = f"{secrets.randbelow(900000) + 100000:06d}"
    # Reuse the existing verified email-code table used by signup. Active users
    # cannot be in the signup-verification flow, so the two flows cannot clash.
    EmailOTP.objects.update_or_create(
        user=user,
        defaults={
            "otp": otp,
            "expires_at": timezone.now() + timedelta(minutes=10),
            "attempts": 0,
            "is_verified": False,
        },
    )
    return _send_otp_email(
        user,
        "Reset your ZIYAMART password",
        "emails/password_reset_otp.html",
        {"user": user, "otp": otp},
    )
