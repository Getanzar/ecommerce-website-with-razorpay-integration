from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [

    # Authentication
    path(
        "signup/",
        views.signup_view,
        name="signup",
    ),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(
            next_page="/"
        ),
        name="logout",
    ),

    # Email OTP Verification
    path(
        "verify-otp/",
        views.verify_otp,
        name="verify_otp",
    ),

    # Profile
    path(
        "profile/",
        views.profile,
        name="profile",
    ),

    path(
        "profile/details/",
        views.profile_detail,
        name="profile_detail",
    ),

    path(
        "sell-with-us/",
        views.seller_application,
        name="seller_application",
    ),
    path("seller/payout-setup/", views.seller_payout_setup, name="seller_payout_setup"),

    # Password Change
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url="/accounts/password/change/done/",
        ),
        name="password_change",
    ),

    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),

    # Password Reset
    path(
        "password/reset/",
        views.password_reset_request,
        name="password_reset",
    ),
    path("password/reset/verify/", views.password_reset_verify, name="password_reset_verify"),
    path("password/reset/resend/", views.password_reset_resend, name="password_reset_resend"),
    path("password/reset/new-password/", views.password_reset_confirm, name="password_reset_confirm"),

]
