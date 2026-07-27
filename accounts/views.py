from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from orders.models import Order

from .forms import SignUpForm
from .models import UserProfile, EmailOTP
from .utils import send_email_otp

def signup_view(request):

    if request.method == "POST":

        form = SignUpForm(request.POST)

        if form.is_valid():

            user = form.save()

            # Store email in session for future OTP verification
            request.session["pending_verification_email"] = user.email

            messages.success(
                request,
                "Account created successfully."
            )

            # Temporary: skip email OTP
            login(request, user)

            return redirect("home")

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