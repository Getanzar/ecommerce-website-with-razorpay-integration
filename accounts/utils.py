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


def request_username_reminder(email, ip=""):
    """Send only to the stored email; never disclose usernames in a response."""
    import hashlib
    from django.core.cache import cache
    from django.contrib.auth.models import User
    email = email.strip().lower()
    digest = hashlib.sha256(email.encode()).hexdigest()
    if not cache.add(f"username-reminder:{digest}", True, 60):
        return
    # Shared website/API hourly limits; identifiers are hashed in cache keys.
    for kind, value, limit in (("email", email, 5), ("ip", ip, 20)):
        key = "username-reminder-hour:" + kind + hashlib.sha256(value.encode()).hexdigest()
        if cache.add(key, 1, 3600):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                return
        if count > limit:
            return
    from django.db.models.functions import Lower, Trim
    user = User.objects.annotate(identity=Lower(Trim("email"))).filter(identity=email, is_active=True).first()
    if user:
        try:
            send_transactional_email(to_email=user.email.strip(), to_name=user.get_full_name(), subject="Your ZIYAMART username", html_content=render_to_string("emails/username_reminder.html", {"user": user}))
        except Exception:
            logger.exception("Username reminder could not be sent")


def send_profile_email_otp(email, otp):
    try:
        return send_transactional_email(to_email=email, to_name="", subject="Verify your new ZIYAMART email", html_content=render_to_string("emails/profile_email_otp.html", {"otp": otp}))
    except Exception:
        logger.exception("Profile email verification could not be sent")
        return False
