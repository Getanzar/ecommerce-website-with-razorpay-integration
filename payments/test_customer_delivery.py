from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .pricing import DeliveryQuoteError, build_parcel_pricing, quote_delhivery


@override_settings(DELHIVERY_API_KEY="test", DELHIVERY_REQUIRE_LIVE_QUOTE=True,
                   PARCEL_CUSTOMER_DELIVERY_LIVE_QUOTES=True, DELHIVERY_GST_PERCENT="18")
class CustomerDeliveryQuoteTests(SimpleTestCase):
    def item(self, pincode):
        seller = Mock(business_pincode=pincode, is_small_seller=False)
        product = SimpleNamespace(
            seller=seller, effective_gst_rate=Decimal("0"), package_weight_grams=500,
            package_length_cm=10, package_width_cm=10, package_height_cm=10,
        )
        variant = SimpleNamespace(seller_price=Decimal("100"), final_price=Decimal("110"))
        return {"product": product, "variant": variant, "quantity": 1}

    @patch("delivery.coverage.has_local_coverage", return_value=False)
    @patch("payments.pricing.requests.get")
    def test_multiple_sellers_charge_customer_each_delivery_once(self, get, coverage):
        get.side_effect = [
            Mock(json=Mock(return_value=[{"gross_amount": "50", "total_amount": "59"}])),
            Mock(json=Mock(return_value=[{"gross_amount": "100", "total_amount": "118"}])),
        ]
        pricing, quotes = build_parcel_pricing(
            [self.item("110001"), self.item("243638")], {"pincode": "243001"}, "cod",
        )
        self.assertEqual(pricing["customer_delivery_charge"], Decimal("177.00"))
        self.assertEqual(pricing["delivery_gst"], Decimal("27.00"))
        self.assertEqual(pricing["seller_sponsored_delivery"], Decimal("0.00"))
        self.assertEqual(sum(q["customer_collection_amount"] for q in quotes), pricing["grand_total"])
        self.assertTrue(all(q["quote_payload"]["delivery_payer"] == "customer" for q in quotes))
        self.assertEqual([c.kwargs["params"]["o_pin"] for c in get.call_args_list], ["110001", "243638"])
        self.assertTrue(all(c.kwargs["params"]["d_pin"] == "243001" for c in get.call_args_list))

    @patch("payments.pricing.requests.get")
    def test_invalid_or_zero_rate_cannot_be_charged(self, get):
        for payload in ([{"total_amount": "0"}], [{"total_amount": "-1"}],
                        {"error": "Invalid PIN", "amount": 50},
                        [{"gross_amount": 100, "total_amount": 90}]):
            get.return_value = Mock(json=Mock(return_value=payload))
            with self.subTest(payload=payload), self.assertRaises(DeliveryQuoteError):
                quote_delhivery("110001", "243001", 500, "online")

    @override_settings(DELHIVERY_API_KEY="", DELHIVERY_REQUIRE_LIVE_QUOTE=False)
    @patch("delivery.coverage.has_local_coverage", return_value=False)
    def test_customer_checkout_requires_live_rate_even_if_legacy_fallback_enabled(self, coverage):
        with self.assertRaises(DeliveryQuoteError):
            build_parcel_pricing([self.item("110001")], {"pincode": "243001"}, "online")
