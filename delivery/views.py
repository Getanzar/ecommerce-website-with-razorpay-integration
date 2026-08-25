from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DeliveryAgentPayoutSetupForm, DeliveryAgentRegistrationForm, DeliveryOTPForm
from .models import DeliveryAgentProfile, LocalDelivery
from .services import complete_delivery, issue_delivery_otp, otp_is_valid


def register(request):
    if request.user.is_authenticated and hasattr(request.user, "delivery_agent"):
        return redirect("delivery_dashboard")
    if request.user.is_authenticated:
        messages.info(request, "Please use a separate account for delivery-agent work.")
        return redirect("home")
    form = DeliveryAgentRegistrationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            profile = form.save(commit=False)
            profile.user = user
            profile.save()
        login(request, user)
        messages.success(request, "Application submitted. An admin must verify you before orders appear.")
        return redirect("delivery_dashboard")
    return render(request, "delivery/register.html", {"form": form})


def _agent(request):
    return get_object_or_404(DeliveryAgentProfile, user=request.user)


@login_required
def dashboard(request):
    agent = _agent(request)
    available = LocalDelivery.objects.none()
    if agent.can_deliver:
        available = LocalDelivery.objects.filter(
            pincode=agent.pincode, status="available", agent__isnull=True
        ).select_related("grocery_order", "food_order")
    active = agent.deliveries.exclude(status__in=("delivered", "cancelled")).select_related(
        "grocery_order", "food_order"
    )
    history = agent.deliveries.filter(status="delivered")[:20]
    earnings = agent.earnings.aggregate(total=Sum("net_amount"))["total"] or Decimal("0.00")
    return render(request, "delivery/dashboard.html", {
        "agent": agent, "available": available, "active": active,
        "history": history, "earnings": earnings,
    })


@login_required
def payout_setup(request):
    agent = _agent(request)
    form = DeliveryAgentPayoutSetupForm(request.POST or None, initial={
        "bank_account_holder": agent.bank_account_holder,
        "bank_ifsc_code": agent.bank_ifsc_code,
    })
    if request.method == "POST" and form.is_valid():
        agent.bank_account_holder = form.cleaned_data["bank_account_holder"]
        agent.bank_account_last4 = form.cleaned_data["bank_account_number"][-4:]
        agent.bank_ifsc_code = form.cleaned_data["bank_ifsc_code"]
        agent.save(update_fields=["bank_account_holder", "bank_account_last4", "bank_ifsc_code", "updated_at"])
        try:
            from .payouts import AgentPayoutError, provision_agent_payout_account
            provision_agent_payout_account(agent, form.cleaned_data["bank_account_number"])
            messages.success(request, "Payout details submitted for admin verification.")
            return redirect("delivery_dashboard")
        except AgentPayoutError as exc:
            messages.error(request, str(exc))
    return render(request, "delivery/payout_setup.html", {"agent": agent, "form": form})


@login_required
@require_POST
def toggle_online(request):
    agent = _agent(request)
    if agent.status != "approved":
        messages.error(request, "Your account must be approved before going online.")
    else:
        agent.is_online = not agent.is_online
        agent.save(update_fields=["is_online", "updated_at"])
    return redirect("delivery_dashboard")


@login_required
@require_POST
@transaction.atomic
def accept_delivery(request, delivery_id):
    agent = _agent(request)
    if not agent.can_deliver:
        messages.error(request, "You must be approved and online to accept an order.")
        return redirect("delivery_dashboard")
    delivery = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=delivery_id)
    if delivery.pincode != agent.pincode:
        messages.error(request, "This order belongs to another delivery pincode.")
    elif delivery.status != "available" or delivery.agent_id is not None:
        messages.error(request, "This order is no longer available.")
    else:
        delivery.agent = agent
        delivery.status = "assigned"
        delivery.assigned_at = timezone.now()
        delivery.save(update_fields=["agent", "status", "assigned_at", "updated_at"])
        messages.success(request, f"Delivery #{delivery.pk} is assigned to you.")
    return redirect("delivery_dashboard")


@login_required
@require_POST
@transaction.atomic
def update_delivery(request, delivery_id):
    agent = _agent(request)
    delivery = get_object_or_404(
        LocalDelivery.objects.select_for_update(), pk=delivery_id, agent=agent
    )
    next_status = request.POST.get("status", "")
    transitions = {
        "assigned": "accepted",
        "accepted": "picked_up",
        "picked_up": "out_for_delivery",
    }
    if transitions.get(delivery.status) != next_status:
        messages.error(request, "That delivery status change is not allowed.")
        return redirect("delivery_dashboard")
    delivery.status = next_status
    fields = ["status", "updated_at"]
    if next_status == "picked_up":
        delivery.picked_up_at = timezone.now()
        fields.append("picked_up_at")
        issue_delivery_otp(delivery)
    delivery.save(update_fields=fields)
    messages.success(request, f"Delivery updated to {delivery.get_status_display()}.")
    return redirect("delivery_dashboard")


@login_required
@transaction.atomic
def complete_with_otp(request, delivery_id):
    agent = _agent(request)
    delivery = get_object_or_404(
        LocalDelivery.objects.select_for_update(), pk=delivery_id, agent=agent
    )
    form = DeliveryOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if delivery.status != "out_for_delivery":
            messages.error(request, "The order must be out for delivery first.")
        elif not otp_is_valid(delivery, form.cleaned_data["otp"]):
            form.add_error("otp", "The OTP is incorrect or expired.")
        else:
            complete_delivery(delivery, agent)
            messages.success(request, "Delivery completed and earning recorded.")
            return redirect("delivery_dashboard")
    return render(request, "delivery/complete.html", {"delivery": delivery, "form": form})


@login_required
def track_delivery(request, public_id):
    delivery = get_object_or_404(LocalDelivery, public_id=public_id)
    if delivery.source_order.user_id != request.user.id and not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return render(request, "delivery/track.html", {"delivery": delivery})


@login_required
@require_POST
def update_location(request, delivery_id):
    """Accept GPS only from the assigned agent during an active delivery."""
    agent = _agent(request)
    delivery = get_object_or_404(LocalDelivery, pk=delivery_id, agent=agent)
    if delivery.status not in {"accepted", "picked_up", "out_for_delivery"}:
        return JsonResponse({"error": "Live tracking is not active for this delivery."}, status=409)
    try:
        latitude = Decimal(request.POST.get("latitude", ""))
        longitude = Decimal(request.POST.get("longitude", ""))
        accuracy = max(0, min(int(float(request.POST.get("accuracy", "0"))), 100000))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"error": "Invalid location coordinates."}, status=400)
    if not (Decimal("-90") <= latitude <= Decimal("90")) or not (Decimal("-180") <= longitude <= Decimal("180")):
        return JsonResponse({"error": "Location coordinates are outside the valid range."}, status=400)
    delivery.agent_latitude = latitude
    delivery.agent_longitude = longitude
    delivery.location_accuracy_meters = accuracy
    delivery.location_updated_at = timezone.now()
    delivery.save(update_fields=[
        "agent_latitude", "agent_longitude", "location_accuracy_meters",
        "location_updated_at", "updated_at",
    ])
    return JsonResponse({"ok": True, "updated_at": delivery.location_updated_at.isoformat()})


@login_required
def live_location(request, public_id):
    """Expose an active agent location only to the order owner or staff."""
    delivery = get_object_or_404(LocalDelivery, public_id=public_id)
    if delivery.source_order.user_id != request.user.id and not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    location_available = delivery.agent_latitude is not None and delivery.agent_longitude is not None
    return JsonResponse({
        "status": delivery.status,
        "status_label": delivery.get_status_display(),
        "available": location_available,
        "latitude": float(delivery.agent_latitude) if location_available else None,
        "longitude": float(delivery.agent_longitude) if location_available else None,
        "accuracy": delivery.location_accuracy_meters if location_available else None,
        "updated_at": delivery.location_updated_at.isoformat() if delivery.location_updated_at else None,
        "tracking_complete": delivery.status in {"delivered", "cancelled"},
    })
