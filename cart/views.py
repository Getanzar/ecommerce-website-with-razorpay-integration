from django.shortcuts import render, redirect, get_object_or_404
from products.models import Product, ProductVariant
from .cart import Cart


# ---------------------------
# CART DETAIL
# ---------------------------
def cart_detail(request):
    cart = Cart(request)

    cart_items = list(cart)
    total_price = cart.get_total_price()

    return render(request, "orders/cart.html", {
        "cart_items": cart_items,
        "total_price": total_price,
    })


# ---------------------------
# ADD TO CART (CLEAN VERSION)
# ---------------------------
def cart_add(request, pid):
    cart = Cart(request)
    product = get_object_or_404(Product, id=pid)

    variant_id = request.POST.get("variant_id")

    if not variant_id:
        return redirect("product_detail_page", slug=product.slug)

    variant = get_object_or_404(
        ProductVariant,
        id=variant_id,
        product=product,
        is_active=True
    )

    # Prevent adding out-of-stock variants
    if variant.stock <= 0:
        return redirect("product_detail_page", slug=product.slug)

    cart.add(
        product=product,
        variant=variant,
        quantity=1
    )

    return redirect("cart_detail")


# ---------------------------
# REMOVE FROM CART (FIXED)
# ---------------------------
def cart_remove(request, pid):
    cart = Cart(request)

    variant = get_object_or_404(ProductVariant, id=pid)

    cart.remove(variant)

    return redirect("cart_detail")


# ---------------------------
# UPDATE CART (FIXED)
# ---------------------------
def cart_update(request, pid):

    cart = Cart(request)

    variant = get_object_or_404(ProductVariant, id=pid)

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
def clear_cart(request):
    cart = Cart(request)

    cart.clear()

    # HARD RESET (fix old broken sessions)
    request.session["cart"] = {}
    request.session.modified = True

    return redirect("cart_detail")

def decrease(request, pid):
    cart = Cart(request)

    variant = get_object_or_404(ProductVariant, id=pid)

    cart.decrease(variant)

    return redirect("cart_detail")