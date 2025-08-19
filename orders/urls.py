from django.urls import path
from . import views

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('success/<int:order_id>/', views.order_success, name='order_success'),
    path('remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('verify/', views.payment_success, name='payment_verify'),

]
