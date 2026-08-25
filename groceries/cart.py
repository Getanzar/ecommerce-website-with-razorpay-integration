from decimal import Decimal

from .models import GroceryProduct


class GroceryCart:
    SESSION_KEY = "grocery_cart"

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(self.SESSION_KEY, {"store_id": None, "items": {}})

    def add(self, product, quantity=1):
        if self.data["store_id"] not in (None, product.store_id):
            raise ValueError("Your grocery cart can contain products from only one store.")
        self.data["store_id"] = product.store_id
        key = str(product.pk)
        self.data["items"][key] = min(self.data["items"].get(key, 0) + quantity, product.stock, 20)
        self.save()

    def remove(self, product_id):
        self.data["items"].pop(str(product_id), None)
        if not self.data["items"]:
            self.data["store_id"] = None
        self.save()

    def set_quantity(self, product, quantity):
        key = str(product.pk)
        if key not in self.data["items"]:
            raise ValueError("That product is not in your grocery cart.")
        if quantity <= 0:
            self.remove(product.pk)
            return
        self.data["items"][key] = min(quantity, product.stock, 20)
        self.save()

    def clear(self):
        self.data = {"store_id": None, "items": {}}
        self.save()

    def save(self):
        self.session[self.SESSION_KEY] = self.data
        self.session.modified = True

    def items(self):
        products = GroceryProduct.objects.select_related("store", "store__seller").filter(pk__in=self.data["items"], is_active=True, stock__gt=0)
        return [{"product": product, "quantity": min(self.data["items"][str(product.pk)], product.stock), "total": product.customer_price * min(self.data["items"][str(product.pk)], product.stock)} for product in products]

    @property
    def subtotal(self):
        return sum((row["total"] for row in self.items()), Decimal("0.00"))
