from django.urls import path
from . import views

urlpatterns = [
    path("", views.grocery_home, name="grocery_home"), path("store/<slug:slug>/", views.store_detail, name="grocery_store"),
    path("cart/", views.cart_detail, name="grocery_cart"), path("cart/add/<int:product_id>/", views.cart_add, name="grocery_cart_add"), path("cart/update/<int:product_id>/", views.cart_update, name="grocery_cart_update"), path("cart/remove/<int:product_id>/", views.cart_remove, name="grocery_cart_remove"),
    path("checkout/", views.checkout, name="grocery_checkout"), path("orders/", views.my_orders, name="grocery_orders"), path("orders/<int:order_id>/success/", views.order_success, name="grocery_order_success"), path("orders/<int:order_id>/payment/", views.payment_retry, name="grocery_payment_retry"), path("orders/<int:order_id>/payment/confirm/", views.payment_confirm, name="grocery_payment_confirm"),
    path("seller/", views.seller_dashboard, name="grocery_seller_dashboard"), path("seller/setup/", views.seller_setup, name="grocery_seller_setup"), path("seller/toggle/", views.seller_toggle_store, name="grocery_seller_toggle"),
    path("seller/products/add/", views.seller_product, name="grocery_seller_add_product"), path("seller/products/<int:product_id>/edit/", views.seller_product, name="grocery_seller_edit_product"), path("seller/orders/", views.seller_orders, name="grocery_seller_orders"), path("seller/orders/<int:order_id>/status/", views.seller_update_order, name="grocery_seller_update_order"),
]
