from django.urls import path
from . import views

urlpatterns = [
    path('clear-cart/', views.clear_cart, name='clear_cart'),
    path('', views.cart_detail, name='cart_detail'),
    path('add/<int:pid>/', views.cart_add, name='cart_add'),
    path('decrease/<int:pid>/', views.decrease, name='decrease'),
    path('remove/<int:pid>/', views.cart_remove, name='cart_remove'),
    path('update/<int:pid>/', views.cart_update, name='cart_update'),
]
