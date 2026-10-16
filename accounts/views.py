import secrets

from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.hashers import make_password, check_password
from django.core.cache import cache
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from orders.models import Order

from .forms import (
    PasswordResetRequestForm,
    SellerApplicationForm,
    SmallSellerApplicationForm,
    SellerPayoutSetupForm,
    SetPasswordWithOTPForm,
    SignUpForm,
    CustomerProfileForm,
)
from .models import EmailOTP, SellerProfile, UserProfile
from .utils import send_email_otp, send_password_reset_otp, request_username_reminder
from .identity import normalize_phone, duplicate_identifiers, DUPLICATE_MESSAGE
from django.core.exceptions import ValidationError


@never_cache
@ensure_csrf_cookie
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("profile_detail")
    seller_route = {"small": "small_seller_application", "small_food": "small_food_seller_application", "small_grocery": "small_grocery_seller_application", "registered": "registered_seller_application"}.get(request.GET.get("seller"))
    if seller_route:
        request.session["seller_signup_next"] = seller_route

    if request.method == "POST":

        form = SignUpForm(request.POST)

        if form.is_valid():

            try:
                # Validation gives useful field errors; the database constraint
                # closes the race where two requests use the same email.
                with transaction.atomic():
                    # Recheck immediately before writing. Besides protecting
                    # against stale/double form submissions, this guarantees
                    # that a duplicate response never leaves a new User behind.
                    duplicate_fields = duplicate_identifiers("", form.cleaned_data["email"], "")
                    if duplicate_fields:
                        for field, error in duplicate_fields.items():
                            form.add_error(field, ValidationError(error, code="existing_account"))
                        return render(request, "accounts/signup.html", {"form": form})
                    user = form.save()
            except IntegrityError:
                form.add_error(
                    None,
                    ValidationError(DUPLICATE_MESSAGE, code="existing_account"),
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
@never_cache
def profile_detail(request):
    user = request.user
    form = CustomerProfileForm(request.POST if request.method == "POST" else None, request.FILES or None, user=user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        pending_email = None
        if data["email"] != user.email.strip().lower():
            key = f"profile-email-change:{user.pk}"
            if not cache.add(key, True, 60):
                form.add_error("email", "Please wait a minute before requesting another email verification code.")
            else:
                from .utils import send_profile_email_otp
                code = f"{secrets.randbelow(900000) + 100000:06d}"
                if send_profile_email_otp(data["email"], code):
                    pending_email = {"email": data["email"], "code_hash": make_password(code), "expires_at": timezone.now().timestamp() + 600, "attempts": 0}
                else:
                    cache.delete(key)
                    form.add_error("email", "We couldn't send a code to the new email. Your current email is unchanged; please try again.")
        if not form.errors:
            profile = user.profile
            for key in ("first_name", "last_name", "username"):
                setattr(user, key, data[key])
            if profile.phone != data["phone"]:
                profile.phone_verified = False
            for key in ("phone", "gender", "date_of_birth"):
                setattr(profile, key, data[key])
            if data.get("profile_picture"):
                profile.profile_picture = data["profile_picture"]
            try:
                with transaction.atomic():
                    user.save()
                    profile.save()
            except IntegrityError:
                form.add_error(None, "Those account details are already registered to another account.")
            else:
                if pending_email:
                    request.session["pending_profile_email"] = pending_email
                    messages.info(request, "Your profile is saved. Verify the code sent to your new email before it becomes your login email.")
                messages.success(request, "Profile updated successfully.")
                return redirect("profile_detail")
    return render(request, "accounts/profile_detail.html", {"form": form, "pending_profile_email": request.session.get("pending_profile_email", {}).get("email")})


@login_required
@require_POST
def verify_profile_email(request):
    pending = request.session.get("pending_profile_email")
    if not pending or pending["expires_at"] < timezone.now().timestamp() or pending["attempts"] >= 5:
        request.session.pop("pending_profile_email", None)
        messages.error(request, "This email verification code expired. Update your email in the profile to request a new code.")
    elif not check_password(request.POST.get("otp", "").strip(), pending["code_hash"]):
        pending["attempts"] += 1
        request.session["pending_profile_email"] = pending
        messages.error(request, "The verification code is incorrect. Please try again.")
    elif duplicate_identifiers("", pending["email"], "", exclude_user_id=request.user.pk):
        request.session.pop("pending_profile_email", None)
        messages.error(request, "This email is already registered to another account.")
    else:
        try:
            with transaction.atomic():
                request.user.email = pending["email"]
                request.user.save(update_fields=["email"])
                request.user.profile.email_verified = True
                request.user.profile.save(update_fields=["email_verified"])
        except IntegrityError:
            messages.error(request, "This email is already registered to another account.")
        else:
            messages.success(request, "Your new email is verified and ready to use for login.")
        request.session.pop("pending_profile_email", None)
    return redirect("profile_detail")


@never_cache
@ensure_csrf_cookie
def seller_application(request):
    if request.user.is_authenticated:
        seller = SellerProfile.objects.filter(user=request.user).first()
        if seller:
            if request.method == "POST":
                return small_seller_application(request) if seller.is_small_seller else registered_seller_application(request)
            return redirect("small_seller_application" if seller.is_small_seller else "registered_seller_application")
    if request.method == "POST":
        return registered_seller_application(request)
    return render(request, "accounts/seller_choice.html")


@login_required
@never_cache
@ensure_csrf_cookie
def registered_seller_application(request):
    return _seller_application_form(request)


@login_required
@never_cache
@ensure_csrf_cookie
def small_seller_application(request, segment="shop"):
    return _seller_application_form(request, small=True, segment=segment)


@login_required
@require_POST
def withdraw_small_seller_consent(request):
    from django.shortcuts import get_object_or_404
    seller = get_object_or_404(SellerProfile, user=request.user, registration_type="small")
    seller.aadhaar_consent_at = None
    seller.aadhaar_last4 = ""
    seller.identity_status = "pending"
    seller.identity_verified_at = None
    seller.identity_verified_by = None
    seller.identity_review_reference = ""
    seller.status = "suspended"
    seller.payouts_enabled = False
    seller.save()
    from dashboard.security import audit
    audit(request, "seller.aadhaar_consent_withdrawn", seller, "Seller withdrew Aadhaar identity-verification consent.")
    messages.info(request, "Aadhaar consent withdrawn. Selling is paused until you reapply and complete identity review.")
    return redirect("small_seller_application")


def _seller_application_form(request, small=False, segment="shop"):
    existing_application = SellerProfile.objects.filter(user=request.user).first()
    if existing_application and existing_application.is_small_seller != small:
        return redirect("small_seller_application" if existing_application.is_small_seller else "registered_seller_application")

    if small and existing_application:
        segment = existing_application.business_segment

    if existing_application and existing_application.is_approved:
        if existing_application.business_segment not in dict(SellerProfile.BUSINESS_SEGMENTS):
            return render(request, "accounts/seller_access.html", {"seller": existing_application})
        return redirect("seller_dashboard")

    if request.method == "POST":
        form_class = SmallSellerApplicationForm if small else SellerApplicationForm
        form = form_class(request.POST, instance=existing_application, **({"segment": segment} if small else {}))
        if form.is_valid():
            seller = form.save(commit=False)
            seller.user = request.user
            seller.status = "pending"
            seller.business_gps_verified_at = timezone.now()
            seller.save()
            if small:
                from dashboard.security import audit
                audit(request, "seller.aadhaar_consent", seller, "Seller consented to offline Aadhaar verification for seller onboarding.", consent_version="small-seller-identity-v1", eligibility_declaration=True)
            if not small and not seller.razorpay_fund_account_id:
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
        form_class = SmallSellerApplicationForm if small else SellerApplicationForm
        form = form_class(instance=existing_application, **({"segment": segment} if small else {}))

    return render(
        request,
        "accounts/seller_application.html",
        {"form": form, "seller": existing_application, "small_seller": small, "segment_label": dict(SellerProfile.BUSINESS_SEGMENTS).get(segment, "")},
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

@never_cache
@transaction.atomic
def verify_otp(request):

    email = request.session.get("pending_verification_email")

    if not email:
        messages.error(
            request,
            "Your verification session has expired. Please sign up again."
        )
        return redirect("signup")

    try:
        user = User.objects.select_for_update().get(email=email)
        otp_record = EmailOTP.objects.get(user=user)

    except (User.DoesNotExist, EmailOTP.DoesNotExist):
        messages.error(
            request,
            "Verification record not found."
        )
        request.session.pop("pending_verification_email", None)
        return redirect("signup")

    if user.is_active or user.profile.email_verified:
        request.session.pop("pending_verification_email", None)

        messages.info(
            request,
            "Your account is already verified. Please login."
        )
        return redirect("login")

    if request.method == "POST":

        entered_otp = request.POST.get("otp", "").strip()

        if otp_record.is_expired():

            messages.error(
                request,
                "Your OTP has expired. Please request a new one."
            )

            return redirect("verify_otp")

        if otp_record.attempts >= 5:
            messages.error(request, "Too many incorrect codes. Please request a new verification code.")
            return redirect("verify_otp")

        if not constant_time_compare(entered_otp, otp_record.otp):

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
        login(request, user, backend="accounts.backends.EmailOrUsernameBackend")

        # Clear session
        request.session.pop("pending_verification_email", None)

        messages.success(
            request,
            "Your account has been verified successfully."
        )

        return redirect(request.session.pop("seller_signup_next", "profile_detail"))

    return render(
        request,
        "accounts/verify_otp.html",
        {
            "email": email,
        },
    )


@never_cache
def forgot_username(request):
    form = PasswordResetRequestForm(request.POST or None)
    sent = False
    if request.method == "POST" and form.is_valid():
        request_username_reminder(form.cleaned_data["email"], request.META.get("REMOTE_ADDR", ""))
        sent = True
    return render(request, "accounts/forgot_username.html", {"form": form, "sent": sent})


@require_POST
@never_cache
def resend_signup_otp(request):
    email = request.session.get("pending_verification_email")
    user = User.objects.filter(email__iexact=email, is_active=False, profile__email_verified=False).first() if email else None
    if not user or not EmailOTP.objects.filter(user=user).exists():
        return redirect("signup")
    if not cache.add(f"website-signup-resend:{user.pk}", True, 60):
        messages.info(request, "Please wait a minute before requesting another code.")
    elif send_email_otp(user):
        messages.success(request, "A new verification code was sent to your email.")
    else:
        cache.delete(f"website-signup-resend:{user.pk}")
        messages.error(request, "We couldn't send a new code. Please try again.")
    return redirect("verify_otp")
