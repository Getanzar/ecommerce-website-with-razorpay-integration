from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Return dictionary[key] if exists, else 0"""
    if dictionary is None:
        return 0
    return dictionary.get(str(key), 0)

@register.filter
def cart_quantity(cart, product_id):
    """Return quantity for a product in the cart dict"""
    product_id = str(product_id)
    if cart and product_id in cart:
        entry = cart[product_id]
        if isinstance(entry, dict):
            return entry.get("quantity", 0)
        return entry  # legacy int
    return 0

@register.filter
def cart_size(cart, product_id):
    """Return size for a product in the cart dict"""
    product_id = str(product_id)
    if cart and product_id in cart:
        entry = cart[product_id]
        if isinstance(entry, dict):
            return entry.get("size", "N/A")
    return "N/A"
