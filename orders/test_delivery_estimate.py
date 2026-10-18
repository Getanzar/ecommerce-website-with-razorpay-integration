import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from orders.commerce import delivery_estimate


class DeliveryEstimateTests(SimpleTestCase):
    def estimate(self, pin):
        request = RequestFactory().get("/orders/delivery-estimate/", {"pincode": pin})
        request.user = SimpleNamespace(is_authenticated=True)
        return delivery_estimate(request)

    def test_invalid_pin_is_rejected(self):
        self.assertEqual(self.estimate("123").status_code, 400)

    @patch("delivery.coverage.has_local_coverage", return_value=True)
    @patch("orders.commerce.Cart")
    def test_mixed_cart_explains_both_timings(self, cart, coverage):
        def item(pin):
            seller = SimpleNamespace(business_pincode=pin, is_small_seller=False)
            return {"product": SimpleNamespace(seller=seller)}
        cart.return_value = [item("243638"), item("110001")]
        text = json.loads(self.estimate("243638").content)["estimate"]
        self.assertIn("3–7 business days after dispatch", text)
        self.assertIn("rider assignment", text)
        self.assertIn("Indicative only", text)

    @patch("delivery.coverage.has_local_coverage", return_value=False)
    @patch("orders.commerce.Cart")
    def test_small_seller_without_coverage_does_not_offer_courier(self, cart, coverage):
        seller = SimpleNamespace(business_pincode="243638", is_small_seller=True, is_approved=True)
        cart.return_value = [{"product": SimpleNamespace(seller=seller)}]
        text = json.loads(self.estimate("243638").content)["estimate"]
        self.assertIn("unavailable", text)
        self.assertNotIn("3–7", text)
