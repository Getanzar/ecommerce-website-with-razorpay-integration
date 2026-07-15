from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('products/', views.product_list_page, name='product_list_page'),
    path('product/<slug:slug>/', views.product_detail_page, name='product_detail_page'),

    path(
    "wishlist/",
    views.wishlist_page,
    name="wishlist_page",
    ),
    path(
    "review/<int:product_id>/",
    views.add_review,
    name="add_review",
),
    path(
        "my-reviews/",
        views.my_reviews,
        name="my_reviews",
    ),

    path(
        "wishlist/<int:product_id>/",
        views.toggle_wishlist,
        name="toggle_wishlist",
    ),

    path("search/", views.search_view, name="search"),
    path("category/<int:category_id>/", views.category_page, name="category_page"),
    path("subcategory/<int:sub_id>/", views.subcategory_products, name="subcategory_products"),  # ✅ added

    # API
    path('api/products/', views.ProductList.as_view(), name='api_products'),
    path('api/products/<slug:slug>/', views.ProductDetail.as_view(), name='api_product_detail'),
]
