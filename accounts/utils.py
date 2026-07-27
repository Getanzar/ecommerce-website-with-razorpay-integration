import random

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOTP


def send_email_otp(user):
    """
    Generate a 6-digit OTP, save/update it,
    and send it to the user's email.
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

    email.send(fail_silently=False)