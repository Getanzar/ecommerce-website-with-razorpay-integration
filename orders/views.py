from decimal import Decimal
from django.http import HttpResponse
from .invoice import generate_invoice
from addresses.models import Address
import requests
import razorpay
import json
import hashlib
import hmac

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render, redirect
from django.views.decorators.csrf import csrf_exempt

from twilio.rest import Client

from cart.cart import Cart
from products.models import Product, ProductVariant

from .forms import CheckoutForm
from .models import (
    Order,
    OrderItem,
    SupportTicket,
    SupportReply,
    ReturnRequest,
    OrderTimeline,
    SellerSettlement,
)
from django.contrib import messages
from django.utils import timezone


@csrf_exempt
def razorpayx_webhook(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    secret = getattr(settings, "RAZORPAYX_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest() if secret else ""
    if not secret or not hmac.compare_digest(signature, expected):
        return HttpResponseBadRequest("Invalid signature")
    try:
        payload = json.loads(request.body)
        payout = payload["payload"]["payout"]["entity"]
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest("Invalid payload")
    settlement = SellerSettlement.objects.filter(provider_payout_id=payout.get("id")).first()
    if not settlement:
        from food.models import FoodSellerSettlement
        settlement = FoodSellerSettlement.objects.filter(provider_payout_id=payout.get("id")).first()
    if settlement:
        provider_status = payout.get("status")
        if provider_status == "processed":
            settlement.status, settlement.processed_at, settlement.failure_reason = "paid", timezone.now(), ""
        elif provider_status in {"rejected", "cancelled", "reversed"}:
            settlement.status = "failed"
            settlement.failure_reason = payout.get("failure_reason") or provider_status
        else:
            settlement.status = "processing"
        settlement.save(update_fields=["status", "processed_at", "failure_reason", "updated_at"])
    return HttpResponse(status=204)

def send_whatsapp_alert(order):
    client = Client("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
    client.messages.create(
        from_="whatsapp:+14155238886",  # Twilio sandbox number
        to="whatsapp:+918279908375",
        body=f"🛒 New Order #{order.id}\nCustomer: {order.full_name}\nAmount: ₹{order.total_price}\nPhone: {order.phone}\nAddress: {order.address}, {order.city} - {order.pincode}"
    )



@login_required
def checkout(request):
    cart = Cart(request)

    addresses = Address.objects.filter(
        user=request.user
    ).order_by("-is_default", "-id")

    if len(cart) == 0:
        return redirect("cart_detail")

    subtotal = cart.get_total_price()
    shipping = Decimal("50.00")
    tax = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))

    total = subtotal + shipping + tax
    total_paise = int(total * 100)

    eta = None
    razorpay_order_id = None

    if request.method == "POST":

        print("\n========== CHECKOUT POST ==========")
        print(request.POST)

        form = CheckoutForm(request.POST)

        print("Form Valid:", form.is_valid())

        if not form.is_valid():
            print(form.errors)

        if form.is_valid():

            payment_method = form.cleaned_data["payment_method"]

            request.session["checkout_data"] = {
                "full_name": form.cleaned_data["full_name"],
                "phone": form.cleaned_data["phone"],
                "address": form.cleaned_data["address"],
                "city": form.cleaned_data["city"],
                "state": form.cleaned_data["state"],
                "pincode": form.cleaned_data["pincode"],
                "payment_method": payment_method,
            }

            eta = get_eta(form.cleaned_data["pincode"])

            # ONLINE PAYMENT
            if payment_method == "online":

                client = razorpay.Client(
                    auth=(
                        settings.RAZORPAY_KEY_ID,
                        settings.RAZORPAY_KEY_SECRET,
                    )
                )

                razorpay_order = client.order.create({
                    "amount": total_paise,
                    "currency": "INR",
                    "payment_capture": 1,
                })

                razorpay_order_id = razorpay_order["id"]

                request.session["razorpay_order_id"] = razorpay_order_id
                request.session["total_paise"] = total_paise

            else:
                razorpay_order_id = None
                request.session["razorpay_order_id"] = ""

            return render(
                request,
                "orders/checkout.html",
                {
                    "form": form,
                    "addresses": addresses,
                    "items": list(cart),
                    "subtotal": subtotal,
                    "shipping": shipping,
                    "tax": tax,
                    "amount_display": f"₹{total:.2f}",
                    "total_paise": total_paise,
                    "currency": "INR",
                    "razorpay_key_id": settings.RAZORPAY_KEY_ID,
                    "razorpay_order_id": razorpay_order_id,
                    "eta": eta,
                    "payment_method": payment_method,
                },
            )

    else:
        form = CheckoutForm(initial={
            "payment_method": "online"
        })

    return render(
        request,
        "orders/checkout.html",
        {
            "form": form,
            "addresses": addresses,
            "items": list(cart),
            "subtotal": subtotal,
            "shipping": shipping,
            "tax": tax,
            "amount_display": f"₹{total:.2f}",
            "total_paise": total_paise,
            "currency": "INR",
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order_id,
            "eta": eta,
        },
    )

@csrf_exempt
def payment_success(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request")

    data = request.POST

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    params_dict = {
        "razorpay_order_id": data.get("razorpay_order_id"),
        "razorpay_payment_id": data.get("razorpay_payment_id"),
        "razorpay_signature": data.get("razorpay_signature"),
    }

    # -------------------------------
    # VERIFY PAYMENT (SECURITY LAYER)
    # -------------------------------
    try:
        client.utility.verify_payment_signature(params_dict)
    except Exception:
        return HttpResponseBadRequest("Payment verification failed")

    # -------------------------------
    # SESSION DATA
    # -------------------------------
    checkout_data = request.session.get("checkout_data")
    cart = request.session.get("cart")

    if not checkout_data or not cart:
        return HttpResponseBadRequest("Session expired. Please try again.")

    # -------------------------------
    # OPTIONAL: EXTRA SECURITY CHECK
    # -------------------------------
    session_order_id = request.session.get("razorpay_order_id")
    if session_order_id and session_order_id != data.get("razorpay_order_id"):
        return HttpResponseBadRequest("Invalid payment session")

# -------------------------------
    # TOTAL PRICE CALCULATION
    # -------------------------------
    subtotal = Decimal("0.00")

    for item in cart.values():
        subtotal += Decimal(str(item["price"])) * item["quantity"]

    shipping = Decimal("50.00")
    tax = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))

    total_price = subtotal + shipping + tax

    # -------------------------------
    # CREATE ORDER
    # -------------------------------
    order = Order.objects.create(
        user=request.user,

        full_name=checkout_data["full_name"],
        phone=checkout_data["phone"],
        address=checkout_data["address"],
        city=checkout_data["city"],
        state=checkout_data["state"],
        pincode=checkout_data["pincode"],

        total_price=total_price,

        # New fields
        status="Processing",
        payment_method=checkout_data["payment_method"],
        payment_status="Paid",

        razorpay_order_id=data["razorpay_order_id"],
        razorpay_payment_id=data["razorpay_payment_id"],
        razorpay_signature=data["razorpay_signature"],
    )

    # -------------------------------
    # ORDER TIMELINE
    # -------------------------------

    OrderTimeline.objects.create(
        order=order,
        event="Order Placed",
        description="Customer placed the order.",
        performed_by=request.user,
    )

    OrderTimeline.objects.create(
        order=order,
        event="Payment Verified",
        description=f"Payment verified via Razorpay. Payment ID: {order.razorpay_payment_id}",
        performed_by=request.user,
    )
    # -------------------------------
    # SAVE ORDER ITEMS
    # -------------------------------
    for item in cart.values():

        product = get_object_or_404(Product, id=item["product_id"])
        variant = get_object_or_404(ProductVariant, id=item["variant_id"])

        # SAFE STOCK CHECK
        if variant.stock < item["quantity"]:
            return HttpResponseBadRequest("Out of stock")

        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,

            product_name=product.name,
            product_image=product.image,

            product_color=variant.color.name if variant else "",
            product_size=variant.size if variant else "",
            product_sku=variant.sku if variant else "",

            quantity=item["quantity"],
            price=Decimal(str(item["price"])),

            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
        )

        variant.stock -= item["quantity"]
        variant.save(update_fields=["stock"])

    from .settlements import create_settlements_for_order
    create_settlements_for_order(order)

    # -------------------------------
    # CLEAR SESSION
    # -------------------------------
    request.session["cart"] = {}
    request.session["checkout_data"] = {}
    request.session["razorpay_order_id"] = None
    request.session.modified = True

    # -------------------------------
    # DELHIVERY SHIPMENT
    # -------------------------------
    url = "https://track.delhivery.com/api/cmu/create.json"

    headers = {
        "Authorization": f"Token {settings.DELHIVERY_API_KEY}"
    }

    payload = {
        "pickup_location": settings.DELHIVERY_PICKUP_LOCATION,
        "shipments": [{
            "add": order.address,
            "phone": order.phone,
            "name": order.full_name,
            "pin": order.pincode,
            "order": str(order.id),
            "payment_mode": "Prepaid",
            "cod_amount": 0,
        }]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        shipment_data = response.json()

        if "packages" in shipment_data:
            order.awb_number = shipment_data["packages"][0]["waybill"]
            order.save()

    except Exception as e:
        print("Delhivery Error:", e)

    from .emails import send_order_confirmation_email
    send_order_confirmation_email(order)

    return redirect("order_success", order_id=order.id)

@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/order_success.html', {'order': order})


def refresh_tracking(order):
    """
    Fetch the latest tracking information from Delhivery.
    Safe for production use.
    """
    if not order.awb_number:
        return

    url = (
        f"https://track.delhivery.com/api/v1/packages/json/"
        f"?waybill={order.awb_number}"
    )

    headers = {
        "Authorization": f"Token {settings.DELHIVERY_API_KEY}"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()

        data = response.json()

        shipment_data = data.get("ShipmentData", [])

        if shipment_data:
            shipment = shipment_data[0]["Shipment"]

            order.delivery_status = shipment.get(
                "Status",
                {}
            ).get(
                "Status",
                "Pending"
            )

            order.eta = shipment.get(
                "ETA",
                "Not Available"
            )

            order.save(
                update_fields=[
                    "delivery_status",
                    "eta",
                ]
            )

    except requests.RequestException as e:
        print(f"Delhivery API Error: {e}")

    except (KeyError, IndexError, TypeError, ValueError) as e:
        print(f"Invalid Delhivery Response: {e}")

@login_required
def my_orders(request):

    status = request.GET.get("status")

    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items", "return_requests")
        .order_by("-created_at")
    )

    if status:
        orders = orders.filter(status=status)

    all_orders = Order.objects.filter(user=request.user)

    context = {
        "orders": orders,
        "selected_status": status,

        "total_orders": all_orders.count(),

        "processing_orders": all_orders.filter(
            status__in=["Pending", "Processing", "Packed"]
        ).count(),

        "shipped_orders": all_orders.filter(
            status__in=["Shipped", "Out for Delivery"]
        ).count(),

        "delivered_orders": all_orders.filter(
            status="Delivered"
        ).count(),

        "cancelled_orders": all_orders.filter(
            status="Cancelled"
        ).count(),

        "returned_orders": all_orders.filter(
            status="Returned"
        ).count(),
    }

    return render(
            request,
            "orders/my_orders.html",
            context,
    )



@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "orders/order_detail.html", {"order": order})

@login_required
def cancel_order(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    # Only allow cancellation before shipment
    if order.status not in ["Pending", "Processing", "Packed"]:
        messages.error(
            request,
            "This order can no longer be cancelled."
        )
        return redirect("order_detail", order_id=order.id)

    if request.method == "POST":

        reason = request.POST.get("reason")

        order.status = "Cancelled"
        order.cancel_reason = reason
        order.cancelled_at = timezone.now()
        order.save()

        messages.success(
            request,
            "Your order has been cancelled successfully."
        )

        return redirect("order_detail", order_id=order.id)

    return render(
        request,
        "orders/cancel_order.html",
        {
            "order": order,
        },
    )

@login_required
def order_support(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
    )

    if request.method == "POST":

        issue = request.POST.get("issue")
        message = request.POST.get("message")

        SupportTicket.objects.create(
            order=order,
            user=request.user,
            issue=issue,
            message=message,
        )

        messages.success(
            request,
            "Your support ticket has been submitted successfully."
        )

        return redirect("order_detail", order_id=order.id)

    return render(
        request,
        "orders/order_support.html",
        {
            "order": order,
        },
    )

@login_required
def return_order(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    # Only delivered orders can be returned
    if order.status != "Delivered":
        messages.error(
            request,
            "Only delivered orders can be returned."
        )
        return redirect("order_detail", order.id)

    # Prevent duplicate requests
    selected_item = request.POST.get("order_item")

    if request.method == "POST":

        if ReturnRequest.objects.filter(
            order=order,
            order_item_id=selected_item,
        ).exists():

            messages.warning(
                request,
                "A return request has already been submitted for this product."
            )

            return redirect(
                "order_detail",
                order.id,
            )

    if request.method == "POST":

        order_item = get_object_or_404(
            OrderItem,
            id=request.POST.get("order_item"),
            order=order,
        )

        ReturnRequest.objects.create(
            order=order,
            order_item=order_item,
            user=request.user,
            reason=request.POST.get("reason"),
            description=request.POST.get("description"),
            image=request.FILES.get("image"),
        )

        messages.success(
            request,
            "Your return request has been submitted."
        )

        return redirect("order_detail", order.id)

    return render(
        request,
        "orders/return_order.html",
        {
            "order": order,
        },
    )


def cart_view(request):
    cart = Cart(request)
    return render(request, 'orders/cart.html', {
        'cart_items': list(cart),
        'total_price': cart.get_total_price(),
    })


def remove_from_cart(request, product_id):
    cart = request.session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        request.session['cart'] = cart
    return redirect('cart')

def get_eta(pincode):
    """Fetch ETA from Delhivery serviceability API safely."""
    url = f"https://track.delhivery.com/c/api/pin-codes/json/?token={settings.DELHIVERY_API_KEY}&pin={pincode}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return "Unable to fetch ETA"

    if "delivery_codes" in data:
        return "3–5 business days"
    return "Not serviceable"

@login_required
def cod_checkout(request):

    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request")

    form = CheckoutForm(request.POST)

    if not form.is_valid():
        return redirect("checkout")

    checkout_data = form.cleaned_data

    cart_service = Cart(request)
    cart = request.session.get("cart")

    if not cart:
        return redirect("cart_detail")

    # =========================================================
    # CALCULATE TOTAL
    # =========================================================

    subtotal = cart_service.get_total_price()

    shipping = Decimal("50.00")

    tax = (
        subtotal * Decimal("0.05")
    ).quantize(Decimal("0.01"))

    total_price = subtotal + shipping + tax

    # =========================================================
    # CREATE ORDER
    # =========================================================

    order = Order.objects.create(
        user=request.user,

        full_name=checkout_data["full_name"],
        phone=checkout_data["phone"],
        address=checkout_data["address"],
        city=checkout_data["city"],
        state=checkout_data["state"],
        pincode=checkout_data["pincode"],

        total_price=total_price,

        status="Pending",
        payment_method="cod",
        payment_status="Pending",
    )

    # =========================================================
    # ORDER TIMELINE
    # =========================================================

    OrderTimeline.objects.create(
        order=order,
        event="Order Placed",
        description="Customer placed a Cash on Delivery order.",
        performed_by=request.user,
    )

    # =========================================================
    # SAVE ORDER ITEMS + REDUCE STOCK
    # =========================================================

    for item in cart.values():

        product = get_object_or_404(
            Product,
            id=item["product_id"]
        )

        variant = get_object_or_404(
            ProductVariant,
            id=item["variant_id"]
        )

        # -------------------------
        # STOCK CHECK
        # -------------------------

        if variant.stock < item["quantity"]:

            # Remove the order because the item
            # is no longer available.
            order.delete()

            return HttpResponseBadRequest(
                f"{product.name} is out of stock."
            )

        # -------------------------
        # CREATE ORDER ITEM
        # -------------------------

        OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,

            product_name=product.name,
            product_image=product.image,

            product_color=(
                variant.color.name
                if variant.color
                else ""
            ),

            product_size=(
                variant.size
                if variant.size
                else ""
            ),

            product_sku=(
                variant.sku
                if variant.sku
                else ""
            ),

            quantity=item["quantity"],
            price=Decimal(str(item["price"])),

            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
        )

        # -------------------------
        # REDUCE STOCK
        # -------------------------

        variant.stock -= item["quantity"]
        variant.save(update_fields=["stock"])

    # =========================================================
    # DELIVERY DECISION
    # =========================================================

    LOCAL_PINCODE = "243638"

    customer_pincode = str(
        checkout_data["pincode"]
    ).strip()

    # =========================================================
    # CASE 1: SELF DELIVERY
    # =========================================================

    if customer_pincode == LOCAL_PINCODE:

        print("========================================")
        print("SELF DELIVERY ORDER")
        print("Order ID:", order.id)
        print("Pincode:", customer_pincode)
        print("No Delhivery shipment required.")
        print("========================================")

        order.status = "Processing"
        order.save(update_fields=["status"])

        OrderTimeline.objects.create(
            order=order,
            event="Self Delivery",
            description=(
                "Order will be delivered directly by ZiyaMart "
                "because the delivery pincode is local."
            ),
            performed_by=request.user,
        )

    # =========================================================
    # CASE 2: DELHIVERY
    # =========================================================

    else:

        print("========================================")
        print("DELHIVERY DELIVERY")
        print("Order ID:", order.id)
        print("Pincode:", customer_pincode)
        print("Creating Delhivery shipment...")
        print("========================================")

        url = "https://track.delhivery.com/api/cmu/create.json"

        headers = {
            "Authorization": f"Token {settings.DELHIVERY_API_KEY}",
            "Accept": "application/json",
        }

        # ---------------------------------------------------------
        # Delhivery shipment data
        # ---------------------------------------------------------

        shipment_payload = {
            "pickup_location": settings.DELHIVERY_PICKUP_LOCATION,

            "shipments": [
                {
                    "add": order.address,
                    "phone": order.phone,
                    "name": order.full_name,
                    "pin": customer_pincode,
                    "order": str(order.id),

                    "payment_mode": "COD",
                    "cod_amount": float(order.total_price),

                    # Required/commonly expected shipment fields
                    "shipping_mode": "Surface",
                    "quantity": 1,
                }
            ]
        }

        # ---------------------------------------------------------
        # IMPORTANT:
        # This endpoint expects form-encoded POST data.
        # "data" must contain the JSON string.
        # ---------------------------------------------------------

        post_data = {
            "format": "json",
            "data": json.dumps(shipment_payload),
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                data=post_data,
                timeout=15,
            )

            try:
                shipment = response.json()

            except ValueError:
                shipment = {
                    "error": True,
                    "raw_response": response.text,
                }

            print("========== DELHIVERY RESPONSE ==========")
            print("STATUS:", response.status_code)
            print("RESPONSE:", shipment)
            print("========================================")

            # =====================================================
            # SUCCESSFUL SHIPMENT
            # =====================================================

            packages = shipment.get("packages") or []

            if (
                shipment.get("success") is True
                and packages
                and packages[0].get("waybill")
            ):

                awb_number = packages[0]["waybill"]

                order.awb_number = awb_number
                order.status = "Shipped"

                order.save(
                    update_fields=[
                        "awb_number",
                        "status",
                    ]
                )

                OrderTimeline.objects.create(
                    order=order,
                    event="Shipment Created",
                    description=(
                        "Delhivery shipment created successfully. "
                        f"AWB: {awb_number}"
                    ),
                    performed_by=request.user,
                )

                print("========================================")
                print("DELHIVERY SHIPMENT CREATED")
                print("Order ID:", order.id)
                print("AWB:", awb_number)
                print("========================================")

            # =====================================================
            # DELHIVERY REJECTED SHIPMENT
            # =====================================================

            else:

                print("========================================")
                print("DELHIVERY SHIPMENT CREATION FAILED")
                print("Delhivery response:", shipment)
                print("========================================")

                order.status = "Processing"

                order.save(
                    update_fields=["status"]
                )

                OrderTimeline.objects.create(
                    order=order,
                    event="Shipment Pending",
                    description=(
                        "Delhivery shipment could not be created "
                        "automatically. Order requires manual "
                        "shipment processing."
                    ),
                    performed_by=request.user,
                )

        except requests.RequestException as e:

            print("========================================")
            print("DELHIVERY CONNECTION ERROR")
            print(e)
            print("========================================")

            order.status = "Processing"

            order.save(
                update_fields=["status"]
            )

            OrderTimeline.objects.create(
                order=order,
                event="Shipment Pending",
                description=(
                    "Could not connect to Delhivery. "
                    "Shipment requires manual processing."
                ),
                performed_by=request.user,
            )

        except Exception as e:

            print("========================================")
            print("UNEXPECTED DELHIVERY ERROR")
            print(e)
            print("========================================")

            order.status = "Processing"

            order.save(
                update_fields=["status"]
            )

            OrderTimeline.objects.create(
                order=order,
                event="Shipment Pending",
                description=(
                    "An unexpected error occurred while creating "
                    "the Delhivery shipment."
                ),
                performed_by=request.user,
            )

        except Exception as e:

            print(
                "Unexpected Delhivery error:",
                e
            )

            order.status = "Processing"

            order.save(
                update_fields=["status"]
            )

    # =========================================================
    # CLEAR SESSION
    # =========================================================

    request.session["cart"] = {}
    request.session["checkout_data"] = {}

    request.session.pop(
        "razorpay_order_id",
        None
    )

    request.session.modified = True

    from .emails import send_order_confirmation_email
    send_order_confirmation_email(order)

    # =========================================================
    # SUCCESS PAGE
    # =========================================================

    return redirect(
        "order_success",
        order_id=order.id
    )

@login_required
def download_invoice(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
    )

    pdf = generate_invoice(order)

    response = HttpResponse(
        pdf,
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="Invoice-{order.id}.pdf"'
    )

    return response

@login_required
def my_returns(request):

    returns = (
        ReturnRequest.objects
        .filter(user=request.user)
        .select_related("order")
        .order_by("-created_at")
    )

    return render(
        request,
        "orders/my_returns.html",
        {
            "returns": returns,
        }
    )

@login_required
def help_support(request):

    tickets = (
        SupportTicket.objects
        .filter(user=request.user)
        .select_related("order")
        .order_by("-created_at")
    )

    return render(
        request,
        "orders/help_support.html",
        {
            "tickets": tickets,
        }
    )


@login_required
def customer_support_ticket(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket.objects.select_related(
            "order",
        ),
        id=ticket_id,
        user=request.user,
    )

    replies = (
        ticket.replies
        .select_related("user")
        .order_by("created_at")
    )

    return render(
        request,
        "orders/support_ticket.html",
        {
            "ticket": ticket,
            "replies": replies,
        },
    )

@login_required
def customer_reply_support_ticket(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket,
        id=ticket_id,
        user=request.user,
    )

    if request.method == "POST":

        message = request.POST.get("message", "").strip()

        if message:

            SupportReply.objects.create(
                ticket=ticket,
                user=request.user,
                message=message,
                is_staff=False,
            )

            ticket.status = "Open"
            ticket.last_reply_at = timezone.now()
            ticket.save()

            messages.success(
                request,
                "Your message has been sent successfully."
            )

    return redirect(
        "customer_support_ticket",
        ticket_id=ticket.id,
    )
