from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from products.catalog import public_products, sellable_variants
from products.models import Product, ProductVariant
from .cart import Cart


# ---------------------------
# CART DETAIL
# ---------------------------
def cart_detail(request):
    cart = Cart(request)

    cart_items = list(cart)
    total_price = sum((item["payable_subtotal"] for item in cart_items), 0)
    total_tax = sum((item["tax_amount"] for item in cart_items), 0)

    return render(request, "orders/cart.html", {
        "cart_items": cart_items,
        "total_price": total_price,
        "total_tax": total_tax,
    })


# ---------------------------
# ADD TO CART (CLEAN VERSION)
# ---------------------------
@require_POST
def cart_add(request, pid):
    cart = Cart(request)
    product = get_object_or_404(public_products(), id=pid)

    variant_id = request.POST.get("variant_id")

    if not variant_id:
        return redirect("product_detail_page", slug=product.slug)

    variant = get_object_or_404(
        sellable_variants(ProductVariant.objects.select_related("product", "product__seller", "color")),
        id=variant_id,
        product=product,
    )

    cart.add(
        product=product,
        variant=variant,
        quantity=1
    )

    return redirect("cart_detail")


# ---------------------------
# REMOVE FROM CART (FIXED)
# ---------------------------
@require_POST
def cart_remove(request, pid):
    cart = Cart(request)

    variant = get_object_or_404(ProductVariant, id=pid)

    cart.remove(variant)

    return redirect("cart_detail")


# ---------------------------
# UPDATE CART (FIXED)
# ---------------------------
@require_POST
def cart_update(request, pid):

    cart = Cart(request)

    variant = get_object_or_404(
        sellable_variants(ProductVariant.objects.select_related("product", "product__seller", "color")),
        id=pid,
    )

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "increase":

            cart.add(
                product=variant.product,
                variant=variant,
                quantity=1
            )

        elif action == "decrease":

            cart.decrease(variant)

    return redirect("cart_detail")


# ---------------------------
# CLEAR CART (FULL RESET)
# ---------------------------
@require_POST
def clear_cart(request):
    cart = Cart(request)

    cart.clear()

    # HARD RESET (fix old broken sessions)
    request.session["cart"] = {}
    request.session.modified = True

    return redirect("cart_detail")

@require_POST
def decrease(request, pid):
    cart = Cart(request)

    variant = get_object_or_404(ProductVariant, id=pid)

    cart.decrease(variant)

    return redirect("cart_detail")
