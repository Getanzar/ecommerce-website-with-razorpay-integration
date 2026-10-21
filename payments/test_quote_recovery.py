from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from .pricing import DeliveryQuoteError, quote_delhivery


@override_settings(DELHIVERY_API_KEY="test", DELHIVERY_REQUIRE_LIVE_QUOTE=True, DELHIVERY_RATE_TIMEOUT=15)
class QuoteRecoveryTests(SimpleTestCase):
    @patch("payments.pricing.requests.get")
    def test_transient_timeout_recovers_for_both_payment_methods(self, get):
        for method in ("online", "cod"):
            with self.subTest(method=method):
                response = Mock()
                response.json.return_value = [{"gross_amount": "38.72", "total_amount": "45.68"}]
                get.reset_mock()
                get.side_effect = [requests.Timeout(), response]
                quote = quote_delhivery("243638", "110053", 500, method)
                self.assertEqual(quote["carrier_amount"], Decimal("38.72"))
                self.assertEqual(quote["quoted_total"], Decimal("45.68"))
                self.assertEqual(get.call_count, 2)
                self.assertEqual(get.call_args.kwargs["timeout"], 7.5)
                self.assertEqual(get.call_args.kwargs["params"]["d_pin"], "110053")

    @patch("payments.pricing.requests.get")
    def test_rejected_credentials_do_not_retry_or_fall_back(self, get):
        response = Mock(status_code=401)
        get.side_effect = requests.HTTPError(response=response)
        with self.assertRaisesMessage(DeliveryQuoteError, "Courier rate access is unavailable"):
            quote_delhivery("243638", "110053", 500, "online")
        get.assert_called_once()

    @patch("payments.pricing.requests.get", side_effect=requests.Timeout())
    def test_repeated_timeout_keeps_checkout_blocked(self, get):
        with self.assertRaisesMessage(DeliveryQuoteError, "temporarily unavailable"):
            quote_delhivery("243638", "110053", 500, "cod")
        self.assertEqual(get.call_count, 2)

    @patch("payments.pricing.requests.get")
    def test_server_error_recovers(self, get):
        response = Mock()
        response.json.return_value = [{"total_amount": "92.88"}]
        get.side_effect = [requests.HTTPError(response=Mock(status_code=503)), response]
        self.assertEqual(quote_delhivery("243638", "110053", 500, "cod")["quoted_total"], Decimal("92.88"))
