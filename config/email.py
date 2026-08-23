import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)
BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


def send_transactional_email(*, to_email, subject, html_content=None, text_content=None, to_name=""):
    """Send one transactional email through Brevo's HTTP API."""
    api_key = settings.BREVO_API_KEY
    if not api_key:
        logger.error("BREVO_API_KEY is not configured; email to %s was not sent", to_email)
        return False

    sender_email = settings.BREVO_SENDER_EMAIL
    if not sender_email:
        logger.error("BREVO_SENDER_EMAIL is not configured; email to %s was not sent", to_email)
        return False

    payload = {
        "sender": {"name": settings.BREVO_SENDER_NAME, "email": sender_email},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
    }
    if html_content:
        payload["htmlContent"] = html_content
    elif text_content:
        payload["textContent"] = text_content
    else:
        raise ValueError("Transactional email requires HTML or text content.")

    try:
        response = requests.post(
            BREVO_TRANSACTIONAL_EMAIL_URL,
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=settings.BREVO_API_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Brevo could not send transactional email to %s", to_email)
        return False

    return True
