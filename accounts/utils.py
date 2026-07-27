import random
import traceback

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOTP


def send_email_otp(user):
    """
    Generate OTP, save it, and send verification email.
    """

    otp = str(random.randint(100000, 999999))
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

    html_message = render_to_string(
        "emails/email_otp.html",
        {
            "user": user,
            "otp": otp,
        },
    )

    email = EmailMultiAlternatives(
        subject="Your ZIYAMART Verification Code",
        body=f"Your OTP is {otp}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    email.attach_alternative(html_message, "text/html")

    # -------- DEBUG --------
    print("=" * 50)
    print("EMAIL SETTINGS")
    print("=" * 50)
    print("HOST:", settings.EMAIL_HOST)
    print("PORT:", settings.EMAIL_PORT)
    print("TLS:", settings.EMAIL_USE_TLS)
    print("HOST USER:", settings.EMAIL_HOST_USER)
    print("FROM:", settings.DEFAULT_FROM_EMAIL)
    print("TO:", user.email)
    print("=" * 50)

    try:
        sent = email.send(fail_silently=False)
        print("EMAIL SENT SUCCESSFULLY")
        print("EMAIL SEND RESULT:", sent)
        return True

    except Exception as e:
        print("EMAIL OTP ERROR:", repr(e))
        traceback.print_exc()
        return False