from rest_framework.test import APITestCase
from . import test_checkout_delivery as fixtures
from groceries.models import GroceryProduct, GroceryProductOption, GroceryCartItem, GroceryOrder

class GroceryPackCheckoutTests(APITestCase):
    setUp = fixtures.CheckoutDeliveryTests.setUp
    seed = fixtures.CheckoutDeliveryTests.seed
    quote = fixtures.CheckoutDeliveryTests.quote

    def test_two_sizes_are_quoted_and_reserved_independently(self):
        self.seed("grocery")
        product = GroceryProduct.objects.get()
        pack = GroceryProductOption.objects.create(product=product, unit="500 g", price=50, mrp=60, stock=4)
        response = self.client.post("/api/v1/groceries/cart/items/", {"product_id": product.pk, "option_id": pack.pk, "quantity": 2}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(GroceryCartItem.objects.count(), 2)
        quote = self.quote("grocery")
        self.assertEqual(quote.status_code, 201, quote.data)
        payload = {"address_id": self.address.pk, "quote_id": quote.data["quote_id"], "payment_method": "cod", "idempotency_key": "two-packs", "items": [{"product_id": product.pk, "option_id": product.default_option.pk, "quantity": 1}, {"product_id": product.pk, "option_id": pack.pk, "quantity": 2}]}
        response = self.client.post("/api/v1/checkout/grocery/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(set(GroceryOrder.objects.get().items.values_list("unit", "quantity")), {("1 kg", 1), ("500 g", 2)})
        product.refresh_from_db(); pack.refresh_from_db()
        self.assertEqual(product.stock, 4)
        self.assertEqual(pack.stock, 2)

    def test_checkout_rejects_pack_substitution_after_quote(self):
        self.seed("grocery")
        product = GroceryProduct.objects.get()
        pack = GroceryProductOption.objects.create(product=product, unit="500 g", price=50, mrp=60, stock=4)
        quote = self.quote("grocery")
        payload = {"address_id": self.address.pk, "quote_id": quote.data["quote_id"], "payment_method": "cod", "idempotency_key": "wrong-pack", "items": [{"product_id": product.pk, "option_id": pack.pk, "quantity": 1}]}
        response = self.client.post("/api/v1/checkout/grocery/", payload, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertFalse(GroceryOrder.objects.exists())

