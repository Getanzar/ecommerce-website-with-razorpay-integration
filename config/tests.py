from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from .email import BREVO_TRANSACTIONAL_EMAIL_URL, send_transactional_email


@override_settings(
    BREVO_API_KEY="test-api-key",
    BREVO_SENDER_NAME="ZIYAMART",
    BREVO_SENDER_EMAIL="orders@ziyamart.in",
    BREVO_API_TIMEOUT=15,
)
class BrevoTransactionalEmailTests(SimpleTestCase):
    @patch("config.email.requests.post")
    def test_sends_expected_brevo_request(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        post.return_value = response

        sent = send_transactional_email(
            to_email="customer@example.com",
            to_name="Test Customer",
            subject="Order confirmed",
            text_content="Your order is confirmed.",
        )

        self.assertTrue(sent)
        post.assert_called_once_with(
            BREVO_TRANSACTIONAL_EMAIL_URL,
            headers={
                "accept": "application/json",
                "api-key": "test-api-key",
                "content-type": "application/json",
            },
            json={
                "sender": {"name": "ZIYAMART", "email": "orders@ziyamart.in"},
                "to": [{"email": "customer@example.com", "name": "Test Customer"}],
                "subject": "Order confirmed",
                "textContent": "Your order is confirmed.",
            },
            timeout=15,
        )

    @patch("config.email.requests.post", side_effect=requests.Timeout)
    def test_api_failure_returns_false(self, _post):
        self.assertFalse(
            send_transactional_email(
                to_email="customer@example.com",
                subject="OTP",
                text_content="123456",
            )
        )
