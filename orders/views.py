from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from cart.cart import Cart
from .models import Order, OrderItem
from .forms import CheckoutForm
from products.models import Product

import razorpay


@login_required
def checkout(request):
    cart = Cart(request)
    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            # 1️⃣ Create Order in DB
            order = Order.objects.create(
                user=request.user,
                address=form.cleaned_data['address'],
                total_price=cart.get_total_price(),
                status="Pending"
            )

            # Save order items
            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item['product'],
                    quantity=item['quantity'],
                    price=item['price']
                )

            # 2️⃣ Create Razorpay Order
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            razorpay_order = client.order.create({
                "amount": int(order.total_price * 100),  # amount in paise
                "currency": "INR",
                "payment_capture": "1"
            })

            # Save Razorpay order_id in DB
            order.razorpay_order_id = razorpay_order["id"]
            order.save()

            # 3️⃣ Send data to payment page
            context = {
                "order": order,
                "razorpay_key": settings.RAZORPAY_KEY_ID,
                "razorpay_order_id": razorpay_order["id"],
                "amount": int(order.total_price * 100),
                "currency": "INR",
            }
            return render(request, "orders/payment.html", context)
    else:
        form = CheckoutForm()

    return render(request, 'orders/checkout.html', {'cart': cart, 'form': form})


# 4️⃣ Payment Success Callback (Razorpay will send data here)
@csrf_exempt
def payment_success(request):
    if request.method == "POST":
        data = request.POST
        try:
            order = Order.objects.get(razorpay_order_id=data.get("razorpay_order_id"))
        except Order.DoesNotExist:
            return HttpResponseBadRequest("Order not found")

        # Save payment details
        order.razorpay_payment_id = data.get("razorpay_payment_id")
        order.razorpay_signature = data.get("razorpay_signature")
        order.status = "Paid"
        order.save()

        # Clear cart after success
        request.session['cart'] = {}

        return redirect("order_success", order_id=order.id)

    return HttpResponseBadRequest("Invalid request")


@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/order_success.html', {'order': order})


# Simple cart view (session-based)
def cart_view(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = 0

    for product_id, quantity in cart.items():
        product = get_object_or_404(Product, id=product_id)
        subtotal = product.price * quantity
        total_price += subtotal
        cart_items.append({
            'product': product,
            'quantity': quantity,
            'subtotal': subtotal,
        })

    return render(request, 'orders/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })


def remove_from_cart(request, product_id):
    cart = request.session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        request.session['cart'] = cart
    return redirect('cart')
