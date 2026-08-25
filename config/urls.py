from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    path("", include("products.urls")),
    path("accounts/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("orders/cart/", include("cart.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("addresses/", include("addresses.urls")),
    path("food/", include("food.urls")),
    path("groceries/", include("groceries.urls")),
    path("delivery/", include("delivery.urls")),
    path("payments/", include("payments.urls")),
]

# Serve static files only in development
if settings.DEBUG:
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT,
    )
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
