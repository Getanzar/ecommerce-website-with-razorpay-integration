from decimal import Decimal

from .models import MenuItemOption


class FoodCart:
    SESSION_KEY = "food_cart"

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(self.SESSION_KEY, {"restaurant_id": None, "items": {}})

    def add(self, option, quantity=1, note=""):
        restaurant_id = option.item.restaurant_id
        if self.data["restaurant_id"] not in (None, restaurant_id):
            raise ValueError("Your food cart can contain items from only one restaurant.")
        self.data["restaurant_id"] = restaurant_id
        key = str(option.pk)
        current = self.data["items"].get(key, {"quantity": 0, "note": ""})
        current["quantity"] = min(current["quantity"] + quantity, 20)
        current["note"] = note[:300] if option.item.accepts_notes else ""
        self.data["items"][key] = current
        self.save()

    def remove(self, option_id):
        self.data["items"].pop(str(option_id), None)
        if not self.data["items"]:
            self.data["restaurant_id"] = None
        self.save()

    def clear(self):
        self.data = {"restaurant_id": None, "items": {}}
        self.save()

    def save(self):
        self.session[self.SESSION_KEY] = self.data
        self.session.modified = True

    def items(self):
        options = MenuItemOption.objects.select_related("item", "item__restaurant").filter(
            pk__in=self.data["items"].keys(), is_available=True, item__is_available=True
        )
        result = []
        for option in options:
            saved = self.data["items"][str(option.pk)]
            quantity = max(1, int(saved["quantity"]))
            result.append({"option": option, "quantity": quantity, "note": saved.get("note", ""), "total": option.customer_price * quantity})
        return result

    @property
    def subtotal(self):
        return sum((row["total"] for row in self.items()), Decimal("0.00"))
