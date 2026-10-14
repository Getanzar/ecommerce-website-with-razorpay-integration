from decimal import Decimal

from .models import GroceryProduct, GroceryProductOption
from .options import resolve_option


class GroceryCart:
    SESSION_KEY = "grocery_cart"

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(self.SESSION_KEY, {"store_id": None, "items": {}})

    @staticmethod
    def key(product, option):
        return str(product.pk) if option.is_default else f"{product.pk}:{option.pk}"

    def add(self, product, quantity=1, option=None):
        if self.data["store_id"] not in (None, product.store_id):
            raise ValueError("Your grocery cart can contain products from only one store.")
        if quantity < 1 or quantity > 20:
            raise ValueError("Choose between 1 and 20 packs.")
        option = option or resolve_option(product)
        if option.product_id != product.pk or not option.is_active or option.stock <= 0:
            raise ValueError("This pack size is unavailable.")
        self.data["store_id"] = product.store_id
        key = self.key(product, option)
        self.data["items"][key] = min(self.data["items"].get(key, 0) + quantity, option.stock, 20)
        self.save()

    def remove(self, product_id, option_id=None):
        key = str(product_id)
        if option_id:
            option = GroceryProductOption.objects.filter(product_id=product_id, pk=option_id).first()
            if option and not option.is_default:
                key = f"{product_id}:{option.pk}"
        self.data["items"].pop(key, None)
        if not self.data["items"]:
            self.data["store_id"] = None
        self.save()

    def set_quantity(self, product, quantity, option=None):
        option = option or product.default_option
        key = self.key(product, option)
        if key not in self.data["items"]:
            raise ValueError("That pack size is not in your grocery cart.")
        if quantity <= 0:
            self.remove(product.pk, option.pk)
            return
        if not option.is_active or option.stock <= 0:
            raise ValueError("This pack size is unavailable. Remove it from your cart.")
        self.data["items"][key] = min(quantity, option.stock, 20)
        self.save()

    def clear(self):
        self.data = {"store_id": None, "items": {}}
        self.save()

    def save(self):
        self.session[self.SESSION_KEY] = self.data
        self.session.modified = True

    def items(self):
        from payments.pricing import line_charges, money
        product_ids = [key.split(":")[0] for key in self.data["items"] if key.split(":")[0].isdigit()]
        products = {product.pk: product for product in GroceryProduct.objects.select_related("store__seller").filter(pk__in=product_ids)}
        options = list(GroceryProductOption.objects.filter(product_id__in=products))
        by_id = {option.pk: option for option in options}
        defaults = {option.product_id: option for option in options if option.is_default}
        rows, missing = [], []
        for key, quantity in self.data["items"].items():
            parts = key.split(":")
            if not all(part.isdigit() for part in parts) or len(parts) > 2:
                missing.append(key)
                continue
            product = products.get(int(parts[0]))
            option = by_id.get(int(parts[1])) if len(parts) == 2 else defaults.get(int(parts[0]))
            if not product or not option or option.product_id != product.pk:
                missing.append(key)
                continue
            option.product = product
            available = product.is_active and option.is_active and option.stock >= quantity and product.store.accepts_orders and product.store.seller.is_approved
            payable = money(sum(line_charges(option.price, option.customer_price, quantity, product.gst_rate).values()))
            unit_payable = money(sum(line_charges(option.price, option.customer_price, 1, product.gst_rate).values()))
            rows.append({"product": product, "option": option, "quantity": quantity, "total": option.customer_price * quantity, "payable_total": payable, "unit_payable_price": unit_payable, "is_available": available})
        if missing:
            for key in missing:
                self.data["items"].pop(key, None)
            if not self.data["items"]:
                self.data["store_id"] = None
            self.save()
        return rows

    @property
    def subtotal(self):
        return sum((row["total"] for row in self.items()), Decimal("0.00"))
