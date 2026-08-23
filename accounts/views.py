import secrets

from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from orders.models import Order

from .forms import (
    PasswordResetRequestForm,
    SellerApplicationForm,
    SellerPayoutSetupForm,
    SetPasswordWithOTPForm,
    SignUpForm,
)
from .models import EmailOTP, SellerProfile, UserProfile
from .utils import send_email_otp, send_password_reset_otp


def signup_view(request):

    if request.method == "POST":

        form = SignUpForm(request.POST)

        if form.is_valid():

            try:
                # Validation gives useful field errors; the database constraint
                # closes the small race where two requests use the same phone.
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                form.add_error(
                    None,
                    "Those account details were just registered. Please change the username, email, or mobile number.",
                )
                return render(request, "accounts/signup.html", {"form": form})

            # Store email for OTP verification
            request.session["pending_verification_email"] = user.email

            # Send OTP email
            email_sent = send_email_otp(user)

            if email_sent:

                messages.success(
                    request,
                    "We've sent a verification code to your email."
                )

                return redirect("verify_otp")

            else:
                # Do not leave behind a reserved, unusable account when no OTP
                # was delivered. The visitor can safely submit the form again.
                user.delete()
                request.session.pop("pending_verification_email", None)
                messages.error(
                    request,
                    "We couldn't send the verification code. No account was created; please try again."
                )

    else:

        form = SignUpForm()

    return render(
        request,
        "accounts/signup.html",
        {
            "form": form,
        },
    )

@login_required
def profile(request):

    status = request.GET.get("status")

    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related(
            "return_requests",
            "items",
            "items__product",
        )
        .order_by("-created_at")
    )

    if status:
        orders = orders.filter(status=status)

    all_orders = Order.objects.filter(user=request.user)

    context = {
        "orders": orders,
        "selected_status": status,

        "total_orders": all_orders.count(),

        "processing_orders": all_orders.filter(
            status__in=["Pending", "Processing", "Packed"]
        ).count(),

        "shipped_orders": all_orders.filter(
            status__in=["Shipped", "Out for Delivery"]
        ).count(),

        "delivered_orders": all_orders.filter(
            status="Delivered"
        ).count(),

        "cancelled_orders": all_orders.filter(
            status="Cancelled"
        ).count(),

        "returned_orders": all_orders.filter(
            status="Returned"
        ).count(),

        "lang": request.session.get("lang", "en"),
    }

    return render(
        request,
        "accounts/profile.html",
        context,
    )


@login_required
def profile_detail(request):

    if request.method == "POST":

        user = request.user

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()

        # Username already exists
        if (
            username != user.username and
            User.objects.filter(username=username).exists()
        ):
            messages.error(
                request,
                "This username is already taken. Please choose another one."
            )
            return redirect("profile_detail")

        # Email already exists
        if (
            email != user.email and
            User.objects.filter(email=email).exists()
        ):
            messages.error(
                request,
                "An account with this email already exists."
            )
            return redirect("profile_detail")

        user.first_name = first_name
        user.last_name = last_name
        user.username = username
        user.email = email

        profile, created = UserProfile.objects.get_or_create(
            user=user
        )

        profile.phone = request.POST.get("phone", "").strip()
        profile.gender = request.POST.get("gender", "").strip()

        dob = request.POST.get("date_of_birth")

        if dob:
            profile.date_of_birth = dob

        if request.FILES.get("profile_picture"):
            profile.profile_picture = request.FILES["profile_picture"]

        user.save()
        profile.save()

        messages.success(
            request,
            "Profile updated successfully."
        )

        return redirect("profile_detail")

    return render(
        request,
        "accounts/profile_detail.html"
    )


@login_required
@never_cache
@ensure_csrf_cookie
def seller_application(request):
    existing_application = SellerProfile.objects.filter(user=request.user).first()

    if existing_application and existing_application.is_approved:
        return redirect("seller_dashboard")

    if request.method == "POST":
        form = SellerApplicationForm(request.POST, instance=existing_application)
        if form.is_valid():
            seller = form.save(commit=False)
            seller.user = request.user
            seller.status = "pending"
            seller.save()
            if not seller.razorpay_fund_account_id:
                try:
                    from .payouts import PayoutOnboardingError, provision_seller_payout_account
                    provision_seller_payout_account(seller, form.cleaned_data["bank_account_number"])
                except PayoutOnboardingError as exc:
                    messages.warning(request, f"Application saved, but payout setup needs attention: {exc}")
            messages.success(
                request,
                "Your seller application was submitted for review.",
            )
            return redirect("seller_application")
    else:
        form = SellerApplicationForm(instance=existing_application)

    return render(
        request,
        "accounts/seller_application.html",
        {"form": form, "seller": existing_application},
    )


@login_required
@never_cache
@ensure_csrf_cookie
def seller_payout_setup(request):
    seller = SellerProfile.objects.filter(user=request.user).first()
    if not seller:
        messages.error(request, "Submit a seller application before setting up payouts.")
        return redirect("seller_application")

    if request.method == "POST":
        form = SellerPayoutSetupForm(request.POST)
        if form.is_valid():
            seller.bank_account_holder = form.cleaned_data["bank_account_holder"].strip()
            seller.bank_ifsc_code = form.cleaned_data["bank_ifsc_code"]
            seller.bank_account_last4 = form.cleaned_data["bank_account_number"][-4:]
            seller.payouts_enabled = False
            seller.razorpay_fund_account_id = ""
            seller.save(update_fields=["bank_account_holder", "bank_ifsc_code", "bank_account_last4", "razorpay_fund_account_id", "payouts_enabled", "updated_at"])
            try:
                from .payouts import PayoutOnboardingError, provision_seller_payout_account
                provision_seller_payout_account(seller, form.cleaned_data["bank_account_number"])
            except PayoutOnboardingError as exc:
                messages.error(request, f"RazorpayX could not process these details: {exc}")
            else:
                messages.success(request, "Bank details were processed securely. Marketplace review is now pending.")
                return redirect("seller_payouts" if seller.is_approved else "seller_application")
    else:
        form = SellerPayoutSetupForm(initial={
            "bank_account_holder": seller.bank_account_holder,
            "bank_ifsc_code": seller.bank_ifsc_code,
        })
    return render(request, "accounts/seller_payout_setup.html", {"form": form, "seller": seller})


def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user and send_password_reset_otp(user):
                request.session["password_reset_user_id"] = user.id
                request.session.pop("password_reset_verified_user_id", None)
                return redirect("password_reset_verify")
            messages.error(
                request,
                "We could not send a reset code. Check the email address and try again.",
            )
    else:
        form = PasswordResetRequestForm()

    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_verify(request):
    user_id = request.session.get("password_reset_user_id")
    otp_record = EmailOTP.objects.filter(user_id=user_id).select_related("user").first()
    if not otp_record:
        messages.error(request, "Request a new password reset code.")
        return redirect("password_reset")

    if request.method == "POST":
        entered_otp = request.POST.get("otp", "").strip()
        if otp_record.is_expired() or otp_record.attempts >= 5:
            otp_record.delete()
            messages.error(request, "This code has expired. Request a new one.")
            return redirect("password_reset")
        if not secrets.compare_digest(entered_otp, otp_record.otp):
            otp_record.attempts += 1
            otp_record.save(update_fields=["attempts"])
            messages.error(request, "That verification code is not correct.")
        else:
            request.session["password_reset_verified_user_id"] = otp_record.user_id
            return redirect("password_reset_confirm")

    return render(
        request,
        "accounts/password_reset_verify.html",
        {"email": otp_record.user.email},
    )


def password_reset_confirm(request):
    user_id = request.session.get("password_reset_verified_user_id")
    otp_record = EmailOTP.objects.filter(user_id=user_id).select_related("user").first()
    if not otp_record or otp_record.is_expired():
        messages.error(request, "Your reset verification has expired. Request a new code.")
        return redirect("password_reset")

    if request.method == "POST":
        form = SetPasswordWithOTPForm(request.POST)
        if form.is_valid():
            user = otp_record.user
            user.set_password(form.cleaned_data["new_password1"])
            user.save(update_fields=["password"])
            otp_record.delete()
            request.session.pop("password_reset_user_id", None)
            request.session.pop("password_reset_verified_user_id", None)
            messages.success(request, "Password changed. You can now log in.")
            return redirect("login")
    else:
        form = SetPasswordWithOTPForm()

    return render(request, "accounts/password_reset_confirm.html", {"form": form})


def password_reset_resend(request):
    if request.method != "POST":
        return redirect("password_reset")

    user_id = request.session.get("password_reset_user_id")
    user = User.objects.filter(id=user_id, is_active=True).first()
    if not user:
        messages.error(request, "Request a new password reset code.")
        return redirect("password_reset")

    if send_password_reset_otp(user):
        messages.success(request, "A new verification code was sent to your email.")
    else:
        messages.error(request, "We could not send a new code. Please try again.")
    return redirect("password_reset_verify")

def verify_otp(request):

    email = request.session.get("pending_verification_email")

    if not email:
        messages.error(
            request,
            "Your verification session has expired. Please sign up again."
        )
        return redirect("signup")

    try:
        user = User.objects.get(email=email)
        otp_record = EmailOTP.objects.get(user=user)

    except (User.DoesNotExist, EmailOTP.DoesNotExist):
        messages.error(
            request,
            "Verification record not found."
        )
        request.session.pop("pending_verification_email", None)
        return redirect("signup")

    if user.is_active:
        request.session.pop("pending_verification_email", None)

        messages.info(
            request,
            "Your account is already verified. Please login."
        )
        return redirect("login")

    if request.method == "POST":

        entered_otp = request.POST.get("otp", "").strip()

        if otp_record.is_expired():

            otp_record.delete()

            messages.error(
                request,
                "Your OTP has expired. Please request a new one."
            )

            return redirect("verify_otp")

        if entered_otp != otp_record.otp:

            otp_record.attempts += 1
            otp_record.save(update_fields=["attempts"])

            messages.error(
                request,
                "Invalid OTP."
            )

            return redirect("verify_otp")

        # Activate account
        user.is_active = True
        user.save(update_fields=["is_active"])

        # Update profile
        profile = user.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])

        # Remove OTP record
        otp_record.delete()

        # Automatically login
        login(request, user)

        # Clear session
        request.session.pop("pending_verification_email", None)

        messages.success(
            request,
            "Your account has been verified successfully."
        )

        return redirect("home")

    return render(
        request,
        "accounts/verify_otp.html",
        {
            "email": email,
        },
    )
