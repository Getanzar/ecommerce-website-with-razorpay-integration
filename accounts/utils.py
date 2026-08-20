import secrets
import logging

from datetime import timedelta
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOTP


logger = logging.getLogger(__name__)


def _send_otp_email(user, subject, template_name, context):
    html = render_to_string(template_name, context)
    # Set the brand explicitly instead of exposing the SMTP account's profile
    # name (for example, the Gmail username) in the recipient's inbox.
    sender_address = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    branded_from_email = formataddr(("ZIYAMART", sender_address))
    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body="Open this email in an HTML-capable email client.",
            from_email=branded_from_email,
            to=[user.email],
        )
        message.attach_alternative(html, "text/html")
        return message.send(fail_silently=False) == 1
    except Exception:
        logger.exception("ZIYAMART OTP email could not be sent to user %s", user.pk)
        return False


def send_email_otp(user):
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
