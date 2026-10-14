"""Pack selection, storefront prices, and transactional grocery inventory."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Q

from .models import GroceryProduct, GroceryProductOption, GroceryOrderItem


class GroceryInventoryError(ValueError):
    pass


def available_products(queryset=None):
    queryset = queryset if queryset is not None else GroceryProduct.objects.all()
    option_products = GroceryProductOption.objects.filter(is_active=True, stock__gt=0).values("product_id")
    return queryset.filter(is_active=True, pk__in=option_products)


def with_pack_options(queryset):
    return queryset.prefetch_related(Prefetch(
        "options", queryset=GroceryProductOption.objects.filter(is_active=True).order_by("-is_default", "pk"),
        to_attr="pack_options",
    ))


def resolve_option(product, option_id=None):
    options = getattr(product, "pack_options", None)
    if options is None:
        options = list(product.options.filter(is_active=True).order_by("-is_default", "pk"))
    if option_id not in (None, ""):
        try:
            selected = next((option for option in options if option.pk == int(option_id)), None)
        except (ValueError, TypeError):
            selected = None
        if selected is None:
            raise GroceryInventoryError("Choose an available pack size for this product.")
    else:
        selected = next((option for option in options if option.stock > 0), None)
    if selected is None or selected.stock <= 0:
        raise GroceryInventoryError("This pack size is out of stock.")
    selected.product = product
    return selected


def prepare_product(product):
    from payments.pricing import line_charges, money
    options = getattr(product, "pack_options", None)
    if options is None:
        options = list(product.options.filter(is_active=True).order_by("-is_default", "pk"))
        product.pack_options = options
    for option in options:
        option.product = product
        option.display_price = money(sum(line_charges(option.price, option.customer_price, 1, product.gst_rate).values()))
        option.savings = max(Decimal("0.00"), money(option.mrp - option.display_price))
    product.selected_option = resolve_option(product)
    product.display_price = product.selected_option.display_price
    product.savings = product.selected_option.savings
    return product


@transaction.atomic
def lock_grocery_rows(rows):
    product_ids = sorted({row["product"].pk for row in rows})
    products = {product.pk: product for product in GroceryProduct.objects.select_for_update().select_related("store__seller").filter(pk__in=product_ids).order_by("pk")}
    option_ids = {row["option"].pk for row in rows}
    options = {option.pk: option for option in GroceryProductOption.objects.select_for_update().filter(pk__in=option_ids).order_by("pk")}
    locked, quantities = [], {}
    for row in rows:
        product, option = products.get(row["product"].pk), options.get(row["option"].pk)
        quantity = int(row["quantity"])
        if not product or not option or option.product_id != product.pk or not product.is_active or not option.is_active:
            raise GroceryInventoryError("A product or pack size is no longer available. Review your cart.")
        if not product.store.accepts_orders or not product.store.seller.is_approved:
            raise GroceryInventoryError("This grocery seller is no longer accepting orders.")
        if quantity < 1 or quantity > 20:
            raise GroceryInventoryError("Choose between 1 and 20 packs.")
        quantities[option.pk] = quantities.get(option.pk, 0) + quantity
        if quantities[option.pk] > option.stock:
            raise GroceryInventoryError(f"Only {option.stock} of {product.name} ({option.unit}) available. Review your cart.")
        option.product = product
        locked.append({**row, "product": product, "option": option, "quantity": quantity})
    if len({row["product"].store_id for row in locked}) != 1:
        raise GroceryInventoryError("A grocery order can contain products from only one store.")
    return locked


def reserve_order_items(order, locked_rows):
    """Caller holds product and option locks in the order transaction."""
    for row in locked_rows:
        product, option, quantity = row["product"], row["option"], row["quantity"]
        GroceryOrderItem.objects.create(
            order=order, product=product, option=option, product_name=product.name,
            unit=option.unit, unit_price=option.customer_price, quantity=quantity,
        )
        option.stock -= quantity
        option.save(update_fields=["stock"])


@transaction.atomic
def restore_order_stock(order):
    items = list(order.items.all())
    list(GroceryProduct.objects.select_for_update().filter(pk__in=[item.product_id for item in items]).order_by("pk"))
    legacy_products = [item.product_id for item in items if not item.option_id]
    options = {option.pk: option for option in GroceryProductOption.objects.select_for_update().filter(
        Q(pk__in=[item.option_id for item in items if item.option_id]) | Q(product_id__in=legacy_products, is_default=True),
    ).order_by("pk")}
    defaults = {option.product_id: option for option in options.values() if option.is_default}
    for item in items:
        option = options[item.option_id] if item.option_id else defaults[item.product_id]
        option.stock += item.quantity
        option.save(update_fields=["stock"])
