from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from .pricing import build_food_pricing, build_grocery_pricing


@override_settings(RESTAURANT_GST_PERCENT="0")
class LocalCustomerDeliveryPricingTests(SimpleTestCase):
    def test_threshold_and_fixed_fee_for_food_and_groceries(self):
        for builder, key in ((build_food_pricing, "option"), (build_grocery_pricing, "product")):
            for seller_fee in (0, 99):
                for amount, customer_fee in (("199.99", "20.00"), ("200.00", "0.00"), ("200.01", "0.00")):
                    with self.subTest(channel=key, seller_fee=seller_fee, amount=amount):
                        item = SimpleNamespace(price=Decimal(amount), customer_price=Decimal(amount), gst_rate=Decimal("0"))
                        pricing = builder([{key: item, "quantity": 1}], SimpleNamespace(delivery_fee=seller_fee))
                        self.assertEqual(pricing["delivery_fee"], Decimal("20.00"))
                        self.assertEqual(pricing["customer_delivery_charge"], Decimal(customer_fee))
                        self.assertEqual(pricing["seller_sponsored_delivery"], Decimal("20.00") - Decimal(customer_fee))
                        self.assertEqual(pricing["grand_total"], Decimal(amount) + Decimal(customer_fee))
