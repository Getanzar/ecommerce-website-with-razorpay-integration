from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('products/', views.product_list_page, name='product_list_page'),
    path('product/<slug:slug>/', views.product_detail_page, name='product_detail_page'),
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),

    # API
    path('api/products/', views.ProductList.as_view(), name='api_products'),
    path('api/products/<slug:slug>/', views.ProductDetail.as_view(), name='api_product_detail'),
]
