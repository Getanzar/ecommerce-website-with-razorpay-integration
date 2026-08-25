from django.urls import path
from . import views
from . import operations

urlpatterns = [

    # Seller workspace
    path("seller/", views.seller_dashboard, name="seller_dashboard"),
    path("seller/products/", views.seller_products, name="seller_products"),
    path("seller/products/<int:product_id>/edit/", views.seller_edit_product, name="seller_edit_product"),
    path("seller/products/<int:product_id>/inventory/", views.seller_inventory, name="seller_inventory"),
    path("seller/products/<int:product_id>/toggle/", views.seller_toggle_product, name="seller_toggle_product"),
    path("seller/orders/", views.seller_orders, name="seller_orders"),
    path("seller/orders/items/<int:item_id>/status/", views.seller_update_order_item, name="seller_update_order_item"),
    path("seller/payouts/", views.seller_payouts, name="seller_payouts"),
    path("seller/payouts/notifications/read/", views.seller_read_notifications, name="seller_read_notifications"),
    path("seller/catalog-requests/", views.seller_catalog_requests, name="seller_catalog_requests"),
    path(
        "seller/products/add/",
        views.seller_add_product,
        name="seller_add_product",
    ),
    path("seller/ai/copy/", views.seller_ai_generate_copy, name="seller_ai_generate_copy"),
    path("seller/ai/image/", views.seller_ai_enhance_image, name="seller_ai_enhance_image"),
    path("seller/ai/buy/", views.seller_ai_create_order, name="seller_ai_create_order"),
    path("seller/ai/confirm/", views.seller_ai_confirm_payment, name="seller_ai_confirm_payment"),

    # Marketplace seller approval
    path("sellers/", views.sellers_management, name="sellers_management"),
    path(
        "sellers/<int:seller_id>/status/",
        views.update_seller_status,
        name="update_seller_status",
    ),
    path("sellers/<int:seller_id>/verify-payouts/", views.verify_seller_payouts, name="verify_seller_payouts"),

    # Dashboard
    path("", operations.operations_home, name="admin_dashboard"),
    path("search/", operations.global_search, name="ops_search"),
    path("operations/agents/", operations.delivery_agents, name="ops_delivery_agents"),
    path("operations/agents/<int:agent_id>/", operations.delivery_agent_detail, name="ops_delivery_agent_detail"),
    path("operations/agents/<int:agent_id>/status/", operations.update_delivery_agent, name="ops_update_delivery_agent"),
    path("operations/customers/", operations.customers, name="ops_customers"),
    path("operations/customers/<int:customer_id>/", operations.customer_detail, name="ops_customer_detail"),
    path("operations/customers/<int:customer_id>/status/", operations.update_customer, name="ops_update_customer"),
    path("operations/customers/<int:customer_id>/notes/", operations.add_customer_note, name="ops_add_customer_note"),
    path("operations/sellers/<int:seller_id>/", operations.seller_detail, name="ops_seller_detail"),
    path("operations/orders/", operations.unified_orders, name="ops_orders"),
    path("operations/orders/<str:kind>/<int:order_id>/", operations.unified_order_detail, name="ops_order_detail"),
    path("operations/deliveries/", operations.local_deliveries, name="ops_deliveries"),
    path("operations/deliveries/<int:delivery_id>/", operations.local_delivery_detail, name="ops_delivery_detail"),
    path("operations/deliveries/<int:delivery_id>/assign/", operations.assign_delivery, name="ops_assign_delivery"),
    path("operations/payouts/", operations.payouts, name="ops_payouts"),
    path("operations/payouts/delivery/<int:earning_id>/paid/", operations.mark_delivery_earning_paid, name="ops_delivery_earning_paid"),
    path("operations/payouts/cod/<int:remittance_id>/confirm/", operations.confirm_cod_remittance, name="ops_confirm_cod_remittance"),
    path("operations/payouts/shipping/<int:charge_id>/reconcile/", operations.reconcile_delivery_charge, name="ops_reconcile_delivery_charge"),
    path("operations/zones/", operations.zones, name="ops_zones"),
    path("operations/zones/create/", operations.create_zone, name="ops_create_zone"),
    path("operations/zones/<int:zone_id>/toggle/", operations.toggle_zone, name="ops_toggle_zone"),
    path("operations/audit/", operations.audit_log, name="ops_audit"),

    # ===========================
    # MANAGEMENT PAGES
    # ===========================

    
    path("products/", views.products_management, name="products_management"),
    path("products/<int:product_id>/review/", views.review_seller_product, name="review_seller_product"),
    path("catalog-requests/", views.catalog_requests_management, name="catalog_requests_management"),
    path("catalog-requests/<int:request_id>/review/", views.review_catalog_request, name="review_catalog_request"),
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
