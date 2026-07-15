from django.urls import path
from . import views

urlpatterns = [

    # Dashboard
    path("", views.admin_dashboard, name="admin_dashboard"),

    # ===========================
    # MANAGEMENT PAGES
    # ===========================

    
    path("products/", views.products_management, name="products_management"),
    path("categories/", views.categories_management, name="categories_management"),
    path("subcategories/", views.subcategories_management, name="subcategories_management"),
    path("inventory/", views.inventory_management, name="inventory_management"),
    path(
        "inventory/edit/<int:id>/",
        views.edit_inventory,
        name="edit_inventory"
    ),
    path("customers/", views.customers_management, name="customers_management"),
    path("reviews/", views.reviews_management, name="reviews_management"),
    path(
    "reviews/<int:id>/approve/",
    views.approve_review,
    name="approve_review",
),

path(
    "reviews/<int:id>/delete/",
    views.delete_review,
    name="delete_review",
),
    path("returns/", views.returns_management, name="returns_management"),
    path(
    "returns/<int:return_id>/approve/",
    views.approve_return,
    name="approve_return",
),

path(
    "returns/<int:return_id>/reject/",
    views.reject_return,
    name="reject_return",
),
    path("support/", views.support_management, name="support_management"),
    path(
    "support/<int:ticket_id>/",
    views.support_ticket_detail,
    name="support_ticket_detail",
),
    path(
        "support/<int:ticket_id>/reply/",
        views.reply_support_ticket,
        name="reply_support_ticket",
    ),

    path(
        "support/<int:ticket_id>/status/",
        views.update_support_status,
        name="update_support_status",
    ),
    path("analytics/", views.analytics_dashboard, name="analytics_dashboard"),

    # ===========================
    # ORDERS
    # ===========================

    path("dashboard/local-orders/", views.local_orders_list, name="local_orders_list"),
    path("dashboard/shipping-orders/", views.shipping_orders_list, name="shipping_orders_list"),
    path("dashboard/mark-shipped/<int:order_id>/", views.mark_order_shipped, name="mark_order_shipped"),

    # ===========================
    # CATEGORY
    # ===========================

    path("add-category/", views.add_category, name="add_category"),
    path("delete-category/<int:id>/", views.delete_category, name="delete_category"),

    path(
        "ajax/add-category/",
        views.ajax_add_category,
        name="add_category_ajax",
    ),

    path(
        "ajax/add-subcategory/",
        views.ajax_add_subcategory,
        name="add_subcategory_ajax",
    ),

    # ===========================
    # SUB CATEGORY
    # ===========================

    path("add-subcategory/", views.add_subcategory, name="add_subcategory"),
    path("delete-subcategory/<int:id>/", views.delete_subcategory, name="delete_subcategory"),

    # ===========================
    # PRODUCTS
    # ===========================

    path("add-product/", views.add_product, name="add_product"),
    path("edit-product/<int:id>/", views.edit_product, name="edit_product"),
    path("delete-product/<int:id>/", views.delete_product, name="delete_product"),
    path(
    "toggle-product/<int:id>/",
        views.toggle_product_status,
        name="toggle_product_status",
    ),
    path(
        "orders/",
            views.order_management,
            name="orders_management",
        ),

    path(
        "orders/<int:order_id>/",
        views.order_detail_ajax,
        name="order_detail_ajax",
    ),
    path(
        "orders/<int:order_id>/update/",
        views.update_order_status,
        name="update_order_status",
    ),
    path(
        "orders/<int:order_id>/invoice/",
        views.download_invoice,
        name="download_invoice",
    ),
]