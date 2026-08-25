from .models import Category
from .catalog import in_stock_products

def categories_processor(request):
    return {
        "categories": Category.objects.filter(products__in=in_stock_products()).distinct()
    }


def commerce_carts_processor(request):
    """Expose lightweight session counts for each independent storefront cart."""
    marketplace = request.session.get("cart", {})
    food = request.session.get("food_cart", {}).get("items", {})
    grocery = request.session.get("grocery_cart", {}).get("items", {})

    def quantity_total(items):
        total = 0
        for item in items.values() if isinstance(items, dict) else ():
            value = item.get("quantity", 0) if isinstance(item, dict) else item
            try:
                total += max(0, int(value))
            except (TypeError, ValueError):
                continue
        return total

    counts = {
        "marketplace_cart_count": quantity_total(marketplace),
        "food_cart_count": quantity_total(food),
        "grocery_cart_count": quantity_total(grocery),
    }
    counts["all_cart_count"] = sum(counts.values())
    return counts
