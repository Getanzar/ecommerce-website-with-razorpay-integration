from decimal import Decimal

from products.models import Product, ProductVariant


class Cart:
    def __init__(self, request):
        self.session = request.session

        self.cart = self.session.get("cart", {})

        invalid_keys = [
            key
            for key, item in self.cart.items()
            if not isinstance(item, dict) or "variant_id" not in item
        ]

        for key in invalid_keys:
            del self.cart[key]

        self.session["cart"] = self.cart

    def add(self, product, variant, quantity=1):
            """
            Add a product variant to the cart.

            Cart key = Variant ID
            """

            variant_key = str(variant.id)

            if variant_key not in self.cart:

                self.cart[variant_key] = {
                    "product_id": product.id,
                    "variant_id": variant.id,
                    "color": variant.color.name,
                    "size": variant.size,
                    "price": str(variant.final_price),
                    "quantity": quantity,
                }

            else:

                # Don't exceed available stock
                new_qty = self.cart[variant_key]["quantity"] + quantity

                if new_qty <= variant.stock:
                    self.cart[variant_key]["quantity"] = new_qty

            self.save()

    def decrease(self, variant):
            """
            Decrease quantity by one.
            """

            variant_key = str(variant.id)

            if variant_key in self.cart:

                if self.cart[variant_key]["quantity"] > 1:

                    self.cart[variant_key]["quantity"] -= 1

                else:

                    del self.cart[variant_key]

            self.save()

    def remove(self, variant):
                """
                Remove variant completely.
                """

                variant_key = str(variant.id)

                if variant_key in self.cart:
                    del self.cart[variant_key]

                self.save()

    def clear(self):
                self.session["cart"] = {}
                self.save()

    def save(self):
                self.session.modified = True

    def __iter__(self):

                variant_ids = [
                    int(v_id)
                    for v_id in self.cart.keys()
                    if str(v_id).isdigit()
                ]

                variants = {
                    variant.id: variant
                    for variant in ProductVariant.objects.select_related(
                        "product",
                        "color"
                    ).filter(id__in=variant_ids)
                }

                for variant_id, item in self.cart.items():

                    try:
                        variant_id_int = int(variant_id)
                    except (ValueError, TypeError):
                            continue

                    variant = variants.get(variant_id_int)

                    if not variant:
                        continue

                    # Never trust a price persisted in the browser session. Re-price
                    # from the current catalog so marketplace fees cannot be bypassed.
                    current_price = variant.final_price
                    if item.get("price") != str(current_price):
                        item["price"] = str(current_price)
                        self.session.modified = True

                    yield {
                        "product": variant.product,
                        "variant": variant,
                        "color": item["color"],
                        "size": item["size"],
                        "price": current_price,
                        "quantity": item["quantity"],
                        "subtotal": current_price * item["quantity"],
                    }

    def __len__(self):

                return sum(
                    item["quantity"]
                    for item in self.cart.values()
                )

    def get_total_price(self):
                return sum(
                    (item["price"] * item["quantity"] for item in self),
                    Decimal("0.00"),
                )
