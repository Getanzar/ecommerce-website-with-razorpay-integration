from dataclasses import dataclass
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import SellerProfile
from delivery.models import DeliveryAgentProfile, DeliveryEarning, DeliveryZone, LocalDelivery
from food.models import FoodOrder, FoodSellerSettlement, Restaurant
from groceries.models import GroceryOrder, GroceryStore
from orders.models import Order, SellerSettlement
from products.models import Product

from .models import AdminAuditLog, CustomerAdminNote
from .security import audit, operations_admin_required


def _money_total(queryset, field):
    return queryset.aggregate(total=Sum(field))["total"] or Decimal("0.00")


@operations_admin_required
def operations_home(request):
    parcel_paid = Order.objects.filter(payment_status="Paid")
    food_paid = FoodOrder.objects.filter(payment_status="Paid")
    grocery_paid = GroceryOrder.objects.filter(payment_status="Paid")
    pending_sellers = SellerProfile.objects.filter(status="pending")
    pending_agents = DeliveryAgentProfile.objects.filter(status="pending")
    unassigned_jobs = LocalDelivery.objects.filter(status="available", agent__isnull=True)
    context = {
        "total_orders": Order.objects.count() + FoodOrder.objects.count() + GroceryOrder.objects.count(),
        "total_revenue": _money_total(parcel_paid, "total_price") + _money_total(food_paid, "total") + _money_total(grocery_paid, "total"),
        "active_deliveries": LocalDelivery.objects.exclude(status__in=("delivered", "cancelled")).count(),
        "total_customers": User.objects.filter(is_superuser=False, is_staff=False, seller_profile__isnull=True, delivery_agent__isnull=True).count(),
        "pending_seller_count": pending_sellers.count(),
        "pending_agent_count": pending_agents.count(),
        "unassigned_job_count": unassigned_jobs.count(),
        "pending_sellers": pending_sellers.select_related("user")[:6],
        "pending_agents": pending_agents.select_related("user")[:6],
        "unassigned_jobs": unassigned_jobs.select_related("food_order", "grocery_order")[:8],
        "failed_payouts": SellerSettlement.objects.filter(status="failed").count() + FoodSellerSettlement.objects.filter(status="failed").count(),
        "parcel_orders": Order.objects.count(), "food_orders": FoodOrder.objects.count(), "grocery_orders": GroceryOrder.objects.count(),
        "products_count": Product.objects.count(),
        "recent_audit": AdminAuditLog.objects.select_related("actor")[:8],
    }
    return render(request, "dashboard/operations/home.html", context)


@operations_admin_required
def global_search(request):
    query = request.GET.get("q", "").strip()
    context = {"query": query, "customers": [], "sellers": [], "agents": [], "parcel_orders": [], "food_orders": [], "grocery_orders": []}
    if query:
        context.update({
            "customers": User.objects.filter(Q(username__icontains=query) | Q(email__icontains=query), is_superuser=False, is_staff=False, seller_profile__isnull=True, delivery_agent__isnull=True)[:10],
            "sellers": SellerProfile.objects.filter(Q(store_name__icontains=query) | Q(user__email__icontains=query)).select_related("user")[:10],
            "agents": DeliveryAgentProfile.objects.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query)).select_related("user")[:10],
            "parcel_orders": Order.objects.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query) | Q(id__icontains=query))[:10],
            "food_orders": FoodOrder.objects.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query) | Q(id__icontains=query))[:10],
            "grocery_orders": GroceryOrder.objects.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query) | Q(id__icontains=query))[:10],
        })
    return render(request, "dashboard/operations/search.html", context)


@operations_admin_required
def delivery_agents(request):
    agents = DeliveryAgentProfile.objects.select_related("user").annotate(
        completed_count=Count("deliveries", filter=Q(deliveries__status="delivered"))
    )
    status = request.GET.get("status", "").strip()
    pincode = request.GET.get("pincode", "").strip()
    query = request.GET.get("q", "").strip()
    if status: agents = agents.filter(status=status)
    if pincode: agents = agents.filter(pincode=pincode)
    if query: agents = agents.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(user__email__icontains=query))
    agents = agents.order_by("-created_at")
    return render(request, "dashboard/operations/agents.html", {
        "agents": Paginator(agents, 20).get_page(request.GET.get("page")), "selected_status": status,
        "pincode": pincode, "query": query,
        "counts": {key: DeliveryAgentProfile.objects.filter(status=key).count() for key in ("pending", "approved", "suspended", "rejected")},
    })


@operations_admin_required
def delivery_agent_detail(request, agent_id):
    agent = get_object_or_404(DeliveryAgentProfile.objects.select_related("user"), pk=agent_id)
    return render(request, "dashboard/operations/agent_detail.html", {
        "agent": agent,
        "active_jobs": agent.deliveries.exclude(status__in=("delivered", "cancelled"))[:20],
        "history": agent.deliveries.filter(status="delivered")[:20],
        "earnings_total": _money_total(agent.earnings.all(), "amount"),
        "payable_total": _money_total(agent.earnings.filter(status="payable"), "amount"),
    })


@require_POST
@operations_admin_required
def update_delivery_agent(request, agent_id):
    agent = get_object_or_404(DeliveryAgentProfile, pk=agent_id)
    status = request.POST.get("status", "")
    reason = request.POST.get("reason", "").strip()
    if status not in {"approved", "suspended", "rejected"}:
        messages.error(request, "Invalid delivery-agent status.")
    elif status in {"suspended", "rejected"} and not reason:
        messages.error(request, "A reason is required for suspension or rejection.")
    elif status == "approved" and not agent.id_document:
        messages.error(request, "Review and require an identity document before approval.")
    else:
        old = agent.status
        agent.status = status
        agent.is_online = agent.is_online if status == "approved" else False
        agent.verified_at = timezone.now() if status == "approved" else agent.verified_at
        agent.save(update_fields=["status", "is_online", "verified_at", "updated_at"])
        audit(request, "agent.status", agent, f"Delivery agent {agent.full_name}: {old} → {status}", reason=reason)
        messages.success(request, "Delivery-agent status updated.")
    return redirect("ops_delivery_agent_detail", agent_id=agent.pk)


@operations_admin_required
def customers(request):
    customers_qs = User.objects.filter(
        is_superuser=False, is_staff=False, seller_profile__isnull=True, delivery_agent__isnull=True
    ).select_related("profile").annotate(
        parcel_count=Count("orders", distinct=True), food_count=Count("food_orders", distinct=True), grocery_count=Count("grocery_orders", distinct=True)
    ).order_by("-date_joined")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query: customers_qs = customers_qs.filter(Q(username__icontains=query) | Q(email__icontains=query) | Q(profile__phone__icontains=query))
    if status == "active": customers_qs = customers_qs.filter(is_active=True)
    if status == "blocked": customers_qs = customers_qs.filter(is_active=False)
    return render(request, "dashboard/operations/customers.html", {
        "customers": Paginator(customers_qs, 25).get_page(request.GET.get("page")), "query": query, "selected_status": status,
    })


@operations_admin_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(User.objects.select_related("profile"), pk=customer_id, is_superuser=False)
    return render(request, "dashboard/operations/customer_detail.html", {
        "customer": customer, "parcel_orders": customer.orders.all()[:20], "food_orders": customer.food_orders.all()[:20],
        "grocery_orders": customer.grocery_orders.all()[:20], "notes": customer.admin_notes.select_related("author")[:20],
    })


@require_POST
@operations_admin_required
def update_customer(request, customer_id):
    customer = get_object_or_404(User, pk=customer_id, is_superuser=False)
    action = request.POST.get("action")
    reason = request.POST.get("reason", "").strip()
    if action not in {"block", "activate"}:
        messages.error(request, "Invalid customer action.")
    elif action == "block" and not reason:
        messages.error(request, "A reason is required to block an account.")
    else:
        customer.is_active = action == "activate"
        customer.save(update_fields=["is_active"])
        if reason:
            CustomerAdminNote.objects.create(customer=customer, author=request.user, note=f"Account {action}: {reason}")
        audit(request, f"customer.{action}", customer, f"Customer {customer.username} {action}d", reason=reason)
        messages.success(request, "Customer account updated.")
    return redirect("ops_customer_detail", customer_id=customer.pk)


@require_POST
@operations_admin_required
def add_customer_note(request, customer_id):
    customer = get_object_or_404(User, pk=customer_id, is_superuser=False)
    note = request.POST.get("note", "").strip()
    if note:
        CustomerAdminNote.objects.create(customer=customer, author=request.user, note=note)
        audit(request, "customer.note", customer, f"Added administrative note for {customer.username}")
        messages.success(request, "Administrative note added.")
    return redirect("ops_customer_detail", customer_id=customer.pk)


@operations_admin_required
def seller_detail(request, seller_id):
    seller = get_object_or_404(SellerProfile.objects.select_related("user"), pk=seller_id)
    store = GroceryStore.objects.filter(seller=seller).first()
    restaurant = Restaurant.objects.filter(seller=seller).first()
    return render(request, "dashboard/operations/seller_detail.html", {
        "seller": seller, "store": store, "restaurant": restaurant,
        "products": seller.products.all()[:20], "settlements": seller.settlements.all()[:20],
        "food_settlements": seller.food_settlements.all()[:20],
    })


@dataclass
class UnifiedOrderRow:
    kind: str
    order: object
    merchant: str
    total: Decimal
    status: str
    payment_status: str


@operations_admin_required
def unified_orders(request):
    kind = request.GET.get("kind", "all")
    query = request.GET.get("q", "").strip()
    rows = []
    if kind in {"all", "parcel"}:
        qs = Order.objects.select_related("user")
        if query: qs = qs.filter(Q(id__icontains=query) | Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query))
        rows += [UnifiedOrderRow("Parcel", o, "Marketplace", o.total_price, o.status, o.payment_status) for o in qs[:200]]
    if kind in {"all", "food"}:
        qs = FoodOrder.objects.select_related("user", "restaurant")
        if query: qs = qs.filter(Q(id__icontains=query) | Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query))
        rows += [UnifiedOrderRow("Food", o, o.restaurant.name, o.total, o.status, o.payment_status) for o in qs[:200]]
    if kind in {"all", "grocery"}:
        qs = GroceryOrder.objects.select_related("user", "store")
        if query: qs = qs.filter(Q(id__icontains=query) | Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(pincode__icontains=query))
        rows += [UnifiedOrderRow("Grocery", o, o.store.name, o.total, o.status, o.payment_status) for o in qs[:200]]
    rows.sort(key=lambda row: row.order.created_at, reverse=True)
    return render(request, "dashboard/operations/orders.html", {"rows": Paginator(rows, 25).get_page(request.GET.get("page")), "selected_kind": kind, "query": query})


@operations_admin_required
def unified_order_detail(request, kind, order_id):
    if kind == "parcel":
        order = get_object_or_404(Order.objects.select_related("user").prefetch_related("items"), pk=order_id)
        merchant, total, items, delivery = "Marketplace sellers", order.total_price, order.items.all(), None
    elif kind == "food":
        order = get_object_or_404(FoodOrder.objects.select_related("user", "restaurant").prefetch_related("items"), pk=order_id)
        merchant, total, items = order.restaurant.name, order.total, order.items.all()
        delivery = LocalDelivery.objects.filter(food_order=order).select_related("agent").first()
    elif kind == "grocery":
        order = get_object_or_404(GroceryOrder.objects.select_related("user", "store").prefetch_related("items"), pk=order_id)
        merchant, total, items = order.store.name, order.total, order.items.all()
        delivery = LocalDelivery.objects.filter(grocery_order=order).select_related("agent").first()
    else:
        from django.http import Http404
        raise Http404
    return render(request, "dashboard/operations/order_detail.html", {
        "kind": kind, "order": order, "merchant": merchant, "total": total, "items": items, "delivery": delivery,
    })


@operations_admin_required
def local_deliveries(request):
    jobs = LocalDelivery.objects.select_related("agent", "food_order", "grocery_order")
    status = request.GET.get("status", "").strip(); pincode = request.GET.get("pincode", "").strip()
    if status: jobs = jobs.filter(status=status)
    if pincode: jobs = jobs.filter(pincode=pincode)
    return render(request, "dashboard/operations/deliveries.html", {
        "jobs": Paginator(jobs, 25).get_page(request.GET.get("page")), "selected_status": status, "pincode": pincode,
        "agents": DeliveryAgentProfile.objects.filter(status="approved").order_by("pincode", "full_name"),
    })


@operations_admin_required
def local_delivery_detail(request, delivery_id):
    job = get_object_or_404(LocalDelivery.objects.select_related("agent", "food_order", "grocery_order"), pk=delivery_id)
    return render(request, "dashboard/operations/delivery_detail.html", {
        "job": job,
        "agents": DeliveryAgentProfile.objects.filter(status="approved", pincode=job.pincode).order_by("full_name"),
    })


@require_POST
@operations_admin_required
@transaction.atomic
def assign_delivery(request, delivery_id):
    job = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=delivery_id)
    agent = get_object_or_404(DeliveryAgentProfile, pk=request.POST.get("agent_id"), status="approved", pincode=job.pincode)
    if job.status not in {"available", "assigned"}:
        messages.error(request, "Only available or not-yet-accepted assignments can be changed.")
    else:
        old_agent = job.agent
        job.agent = agent; job.status = "assigned"; job.assigned_at = timezone.now()
        job.save(update_fields=["agent", "status", "assigned_at", "updated_at"])
        audit(request, "delivery.assign", job, f"Delivery #{job.pk} assigned to {agent.full_name}", previous_agent_id=getattr(old_agent, "pk", None))
        messages.success(request, "Delivery assignment updated.")
    return redirect("ops_deliveries")


@operations_admin_required
def payouts(request):
    return render(request, "dashboard/operations/payouts.html", {
        "delivery_earnings": DeliveryEarning.objects.select_related("agent", "delivery")[:100],
        "seller_settlements": SellerSettlement.objects.select_related("seller", "order")[:100],
        "food_settlements": FoodSellerSettlement.objects.select_related("seller", "order")[:100],
        "delivery_payable": _money_total(DeliveryEarning.objects.filter(status="payable"), "amount"),
    })


@require_POST
@operations_admin_required
def mark_delivery_earning_paid(request, earning_id):
    earning = get_object_or_404(DeliveryEarning, pk=earning_id)
    if earning.status != "payable": messages.error(request, "Only payable earnings can be marked paid.")
    else:
        earning.status = "paid"; earning.paid_at = timezone.now(); earning.save(update_fields=["status", "paid_at"])
        audit(request, "delivery_earning.paid", earning, f"Marked delivery earning #{earning.pk} paid", amount=str(earning.amount))
        messages.success(request, "Delivery earning marked paid.")
    return redirect("ops_payouts")


@operations_admin_required
def zones(request):
    return render(request, "dashboard/operations/zones.html", {"zones": DeliveryZone.objects.all()})


@require_POST
@operations_admin_required
def create_zone(request):
    pincode = request.POST.get("pincode", "").strip(); city = request.POST.get("city", "").strip(); state = request.POST.get("state", "").strip()
    if len(pincode) != 6 or not pincode.isdigit() or not city: messages.error(request, "A valid pincode and city are required.")
    else:
        zone, created = DeliveryZone.objects.get_or_create(pincode=pincode, defaults={"city": city, "state": state})
        audit(request, "zone.create" if created else "zone.exists", zone, f"Delivery zone {pincode} reviewed")
        messages.success(request, "Delivery zone saved.")
    return redirect("ops_zones")


@require_POST
@operations_admin_required
def toggle_zone(request, zone_id):
    zone = get_object_or_404(DeliveryZone, pk=zone_id); zone.is_active = not zone.is_active; zone.save(update_fields=["is_active"])
    audit(request, "zone.toggle", zone, f"Delivery zone {zone.pincode} {'enabled' if zone.is_active else 'disabled'}")
    return redirect("ops_zones")


@operations_admin_required
def audit_log(request):
    logs = AdminAuditLog.objects.select_related("actor")
    action = request.GET.get("action", "").strip()
    if action: logs = logs.filter(action__icontains=action)
    return render(request, "dashboard/operations/audit.html", {"logs": Paginator(logs, 50).get_page(request.GET.get("page")), "action": action})
