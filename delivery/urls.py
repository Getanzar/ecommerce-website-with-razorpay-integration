from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="delivery_register"),
    path("dashboard/", views.dashboard, name="delivery_dashboard"),
    path("payouts/setup/", views.payout_setup, name="delivery_payout_setup"),
    path("online/", views.toggle_online, name="delivery_toggle_online"),
    path("jobs/<int:delivery_id>/accept/", views.accept_delivery, name="delivery_accept"),
    path("jobs/<int:delivery_id>/status/", views.update_delivery, name="delivery_update"),
    path("jobs/<int:delivery_id>/complete/", views.complete_with_otp, name="delivery_complete"),
    path("jobs/<int:delivery_id>/location/", views.update_location, name="delivery_location_update"),
    path("track/<uuid:public_id>/", views.track_delivery, name="delivery_track"),
    path("track/<uuid:public_id>/location/", views.live_location, name="delivery_live_location"),
]
