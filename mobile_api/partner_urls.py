from django.urls import path
from . import partners as views
from . import partner_forms as forms

urlpatterns = [
    path("seller/profile/", forms.SellerProfileFormView.as_view()),
    path("applications/<str:role>/", forms.ApplicationView.as_view()),
    path("payout-setup/<str:role>/", forms.PayoutSetupView.as_view()),
    path("seller/categories/", forms.SellerCategoryView.as_view()),
    path("seller/products/new/", forms.ProductFormView.as_view()),
    path("seller/products/<int:pk>/edit/", forms.ProductFormView.as_view()),
    path(
    "seller/products/<int:pk>/colors/",
    forms.ProductColorFormView.as_view(),
    ),
    path("seller/<str:kind>/store/", forms.StoreFormView.as_view()),
    path("seller/<str:kind>/products/new/", forms.ServiceProductFormView.as_view()),
    path("seller/<str:kind>/products/<int:pk>/edit/", forms.ServiceProductFormView.as_view()),
    path("seller/<str:kind>/products/<int:pk>/variants/new/", forms.VariantFormView.as_view()),
    path("seller/<str:kind>/products/<int:pk>/variants/<int:variant_pk>/", forms.VariantFormView.as_view()),
    path("roles/", views.RolesView.as_view()),
    path("seller/", views.SellerWorkspaceView.as_view()),
    path("seller/<str:kind>/availability/", views.StoreAvailabilityView.as_view()),
    path("seller/<str:kind>/orders/", views.SellerOrdersView.as_view()),
    path("seller/<str:kind>/orders/<int:pk>/", views.SellerOrderUpdateView.as_view()),
    path("seller/<str:kind>/orders/<int:pk>/cancel/", views.SellerOrderCancelView.as_view()),
    path("seller/<str:kind>/catalog/", views.SellerCatalogView.as_view()),
    path("seller/<str:kind>/catalog/<int:pk>/", views.SellerCatalogUpdateView.as_view()),
    path("seller/<str:kind>/payouts/", views.SellerPayoutsView.as_view()),
    path("rider/online/", views.RiderOnlineView.as_view()),
    path("rider/jobs/", views.RiderJobsView.as_view()),
    path("rider/jobs/<int:pk>/accept/", views.RiderAcceptView.as_view()),
    path("rider/jobs/<int:pk>/status/", views.RiderStatusView.as_view()),
    path("rider/jobs/<int:pk>/complete/", views.RiderCompleteView.as_view()),
    path("rider/jobs/<int:pk>/location/", views.RiderLocationView.as_view()),
    path("rider/earnings/", views.RiderEarningsView.as_view()),
]
