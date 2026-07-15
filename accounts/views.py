from django.shortcuts import render, redirect
from .forms import SignUpForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from orders.models import Order
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import UserProfile
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.urls import reverse
from .tokens import email_verification_token

def signup_view(request):

    if request.method == "POST":

        form = SignUpForm(request.POST)

        if form.is_valid():

            user = form.save()

            current_site = get_current_site(request)

            uid = urlsafe_base64_encode(force_bytes(user.pk))

            token = email_verification_token.make_token(user)

            verification_link = request.build_absolute_uri(
                reverse(
                    "verify_email",
                    kwargs={
                        "uidb64": uid,
                        "token": token,
                    },
                )
            )

            html_message = render_to_string(
                "emails/verify_email.html",
                {
                    "user": user,
                    "verification_link": verification_link,
                    "domain": current_site.domain,
                },
            )

            email = EmailMultiAlternatives(
                subject="Verify your ZIYAMART account",
                body="Please verify your email.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )

            email.attach_alternative(html_message, "text/html")
            try:
                email.send(fail_silently=False)
                print("✅ Email sent successfully")
            except Exception as e:
                print("❌ Email error:", e)
                raise

            messages.success(
                request,
                "Verification email sent. Please check your inbox."
            )

            return redirect("login")

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

def verify_email(request, uidb64, token):

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and email_verification_token.check_token(user, token):

        user.is_active = True
        user.save()

        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.save()

        messages.success(
            request,
            "Your email has been verified successfully. You can now login."
        )

        return redirect("login")

    messages.error(
        request,
        "Verification link is invalid or has expired."
    )

    return redirect("signup")