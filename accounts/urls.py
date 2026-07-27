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
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.html",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url="/accounts/password/reset/done/",
        ),
        name="password_reset",
    ),

    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),

    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/accounts/password/reset/complete/",
        ),
        name="password_reset_confirm",
    ),

    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

]