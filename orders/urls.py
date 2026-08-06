from django.urls import path
from . import views

urlpatterns = [

    # Checkout
    path(
        "checkout/",
        views.checkout,
        name="checkout",
    ),

    path(
        "cod-checkout/",
        views.cod_checkout,
        name="cod_checkout",
    ),

    path(
        "payment-success/",
        views.payment_success,
        name="payment_success",
    ),

    path(
        "success/<int:order_id>/",
        views.order_success,
        name="order_success",
    ),

    # Orders
    path(
        "my-orders/",
        views.my_orders,
        name="my_orders",
    ),

    path(
        "my-returns/",
        views.my_returns,
        name="my_returns",
    ),

    path(
    "help-support/",
    views.help_support,
    name="help_support",
    ),
    path(
        "support/ticket/<int:ticket_id>/",
        views.customer_support_ticket,
        name="customer_support_ticket",
    ),
    path(
        "support/ticket/<int:ticket_id>/reply/",
        views.customer_reply_support_ticket,
        name="customer_reply_support_ticket",
    ),

    path(
        "detail/<int:order_id>/",
        views.order_detail,
        name="order_detail",
    ),

    path(
        "cancel/<int:order_id>/",
        views.cancel_order,
        name="cancel_order",
    ),

    path(
         "support/<int:order_id>/",
         views.order_support,
         name="order_support",
        ),

    path(
        "return/<int:order_id>/",
        views.return_order,
        name="return_order",
    ),
    path(
        "invoice/<int:order_id>/",
        views.download_invoice,
        name="download_invoice",
    ),

    # Cart
    path(
        "remove/<int:product_id>/",
        views.remove_from_cart,
        name="remove_from_cart",
    ),
]