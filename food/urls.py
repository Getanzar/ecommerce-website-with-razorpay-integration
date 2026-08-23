from django.urls import path
from . import views

urlpatterns = [
    path("", views.restaurant_list, name="food_home"),
    path("restaurant/<slug:slug>/", views.restaurant_menu, name="food_restaurant"),
    path("cart/", views.cart_detail, name="food_cart"),
    path("cart/add/<int:option_id>/", views.cart_add, name="food_cart_add"),
    path("cart/remove/<int:option_id>/", views.cart_remove, name="food_cart_remove"),
    path("checkout/", views.checkout, name="food_checkout"),
    path("orders/", views.my_orders, name="food_orders"),
    path("orders/<int:order_id>/success/", views.order_success, name="food_order_success"),
    path("orders/<int:order_id>/payment/confirm/", views.payment_confirm, name="food_payment_confirm"),
    path("seller/menu/", views.seller_menu, name="food_seller_menu"),
    path("seller/setup/", views.seller_restaurant_setup, name="food_seller_setup"),
    path("seller/open-status/", views.seller_toggle_restaurant, name="food_seller_toggle_restaurant"),
    path("seller/menu/add/", views.seller_add_menu_item, name="food_seller_add_item"),
    path("seller/menu/<int:item_id>/edit/", views.seller_edit_menu_item, name="food_seller_edit_item"),
    path("seller/sections/add/", views.seller_add_section, name="food_seller_add_section"),
    path("seller/orders/", views.seller_orders, name="food_seller_orders"),
    path("seller/orders/<int:order_id>/status/", views.seller_update_order, name="food_seller_update_order"),
    path("seller/menu/<int:item_id>/toggle/", views.seller_toggle_item, name="food_seller_toggle_item"),
]
