import random
import requests

from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOTP


def send_email_otp(user):
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

    html = render_to_string(
        "emails/email_otp.html",
        {
            "user": user,
            "otp": otp,
        },
    )

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {
            "name": "ZIYAMART",
            "email": "ulhaqanzar444@gmail.com"
        },
        "to": [
            {
                "email": user.email,
                "name": user.get_full_name() or user.username
            }
        ],
        "subject": "Your ZIYAMART Verification Code",
        "htmlContent": html,
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=30,
        )

        print("BREVO STATUS:", response.status_code)
        print("BREVO RESPONSE:", response.text)

        return response.status_code == 201

    except Exception as e:
        print("BREVO ERROR:", repr(e))
        return False