"""Authenticated mobile workspaces; never accept a seller/agent id from clients."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from accounts.models import SellerProfile
from delivery.models import DeliveryAgentProfile, LocalDelivery
from delivery.services import complete_delivery, issue_delivery_otp, otp_is_valid
from food.models import FoodOrder, FoodSellerSettlement, MenuItem, Restaurant
from groceries.models import GroceryOrder, GroceryProduct, GrocerySellerSettlement, GroceryStore
from orders.models import Order, OrderItem, SellerSettlement
from products.models import Product, ProductVariant


class PartnerThrottle(UserRateThrottle):
    rate = "120/min"


class OTPThrottle(UserRateThrottle):
    scope = "mobile_delivery_otp"
    rate = "5/min"


class PartnerView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PartnerThrottle]


def seller_for(user):
    seller = get_object_or_404(SellerProfile, user=user)
    if not seller.is_approved:
        raise PermissionDenied("Your seller account must be approved first.")
    return seller


def seller_kinds(seller):
    """Authorization uses the saved explicit segment, never free-text labels."""
    return [seller.business_segment] if seller.business_segment in dict(SellerProfile.BUSINESS_SEGMENTS) else []


def require_seller_kind(seller, kind):
    if kind not in seller_kinds(seller):
        raise PermissionDenied("This category is not enabled for your seller account. Contact support to update your registration.")


class SellerKindView(PartnerView):
    """Apply category authorization before reading forms or accepting writes."""
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_seller_kind(seller_for(request.user), kwargs.get("kind", "shop"))


def agent_for(user):
    agent = get_object_or_404(DeliveryAgentProfile, user=user)
    if agent.status != "approved":
        raise PermissionDenied("Your rider account must be approved first.")
    return agent


def page(request, rows, render):
    paginator = PageNumberPagination()
    paginator.page_size = 25
    return paginator.get_paginated_response([render(row) for row in paginator.paginate_queryset(rows, request)])


class RolesView(PartnerView):
    def get(self, request):
        seller = SellerProfile.objects.filter(user=request.user).first()
        agent = DeliveryAgentProfile.objects.filter(user=request.user).first()
        return Response({
            "seller": {"name": seller.store_name, "status": seller.status,
                       "payouts_enabled": seller.payouts_enabled} if seller else None,
            "rider": {"name": agent.full_name, "status": agent.status,
                      "is_online": agent.is_online, "pincode": agent.pincode,
                      "payouts_enabled": agent.payouts_enabled} if agent else None,
        })


class SellerWorkspaceView(PartnerView):
    def get(self, request):
        from .serializers import absolute_url
        seller = seller_for(request.user)
        stores = []
        for kind, model in (("food", Restaurant), ("grocery", GroceryStore)):
            if kind not in seller_kinds(seller):
                continue
            store = model.objects.filter(seller=seller).first()
            if store:
                stores.append({"kind": kind, "name": store.name, "accepts_orders": store.accepts_orders,
                               "image_url": absolute_url(request, store.image), "pincode": store.pincode})
        metrics = {"catalog_count": 0, "open_orders": 0}
        if seller_kinds(seller):
            kind = seller.business_segment
            model, lookup = {"shop": (Product, "seller"), "food": (MenuItem, "restaurant__seller"), "grocery": (GroceryProduct, "store__seller")}[kind]
            metrics["catalog_count"] = model.objects.filter(**{lookup: seller}).count()
            orders = seller_orders(seller, kind)
            if kind == "shop":
                metrics["open_orders"] = orders.exclude(order__status__in=["Cancelled", "Returned", "Delivered"]).exclude(fulfillment_status__in=["delivered", "cancelled"]).values("order_id").distinct().count()
            else:
                metrics["open_orders"] = orders.exclude(status__in=["delivered", "cancelled"]).count()
        return Response({"name": seller.store_name, "stores": stores,
                         "description": seller.description, "pincode": seller.business_pincode,
                         "logo_url": absolute_url(request, seller.logo), "cover_url": absolute_url(request, seller.cover_image),
                         "metrics": metrics,
                         "allowed_kinds": seller_kinds(seller),
                         "business_category": seller.business_category,
                         "business_segment": seller.business_segment,
                         "payouts_enabled": seller.payouts_enabled,
                         "bank_last4": seller.bank_account_last4,
                         "return_balance": str(seller.return_debits.aggregate(total=Sum("remaining_amount"))["total"] or 0)})


class StoreAvailabilityView(SellerKindView):
    def patch(self, request, kind):
        seller = seller_for(request.user)
        model = {"food": Restaurant, "grocery": GroceryStore}.get(kind)
        if model is None:
            raise ValidationError("Unknown store type.")
        value = request.data.get("accepts_orders")
        if not isinstance(value, bool):
            raise ValidationError("accepts_orders must be true or false.")
        store = get_object_or_404(model, seller=seller)
        store.accepts_orders = value
        store.save(update_fields=["accepts_orders"])
        return Response({"accepts_orders": value})


PARCEL_NEXT = {"new": "accepted", "accepted": "packed", "packed": "shipped"}
FOOD_NEXT = {"placed": "accepted", "accepted": "preparing", "preparing": "ready"}
GROCERY_NEXT = {"placed": "accepted", "accepted": "packing", "packing": "ready"}


def seller_orders(seller, kind):
    require_seller_kind(seller, kind)
    if kind == "shop":
        return OrderItem.objects.filter(product__seller=seller).select_related("order", "product").order_by("-order__created_at", "-pk")
    if kind == "food":
        return FoodOrder.objects.filter(restaurant__seller=seller).prefetch_related("items").order_by("-created_at", "-pk")
    if kind == "grocery":
        return GroceryOrder.objects.filter(store__seller=seller).prefetch_related("items").order_by("-created_at", "-pk")
    raise ValidationError("Unknown order type.")


def order_next(row, kind):
    order = row.order if kind == "shop" else row
    if order.status.lower() in {"cancelled", "returned", "delivered"}:
        return None
    if order.payment_method != "cod" and order.payment_status != "Paid":
        return None
    if kind == "shop":
        next_status = PARCEL_NEXT.get(row.fulfillment_status)
        if next_status == "shipped" and order.local_deliveries.filter(parcel_seller_id=row.product.seller_id).exists():
            return None  # Local rider owns pickup and completion.
        return next_status
    return (FOOD_NEXT if kind == "food" else GROCERY_NEXT).get(order.status)


def order_data(row, kind):
    order = row.order if kind == "shop" else row
    items = [{"name": row.product_name, "quantity": row.quantity,
              "variant": " / ".join(filter(None, [row.product_color, row.product_size]))}] if kind == "shop" else [
        {"name": item.item_name if kind == "food" else item.product_name,
         "quantity": item.quantity,
         "variant": item.option_name if kind == "food" else item.unit} for item in row.items.all()]
    return {"id": row.pk, "order_id": order.pk, "kind": kind,
            "status": row.fulfillment_status if kind == "shop" else row.status,
            "payment_status": order.payment_status, "payment_method": order.payment_method,
            "customer": order.full_name, "address": f"{order.address}, {order.city}, {order.pincode}",
            "items": items, "amount": str(row.seller_total if kind == "shop" else row.subtotal),
            "created_at": order.created_at, "next_status": order_next(row, kind),
            "can_cancel": (row.fulfillment_status if kind == "shop" else row.status) in {
                "shop": {"new", "accepted", "packed"}, "food": {"placed", "accepted"},
                "grocery": {"placed", "accepted", "packing"},
            }[kind] and order.status.lower() not in {"cancelled", "returned", "delivered"},
            "courier": row.seller_courier if kind == "shop" else "",
            "tracking_number": row.seller_tracking_number if kind == "shop" else ""}


class SellerOrdersView(SellerKindView):
    def get(self, request, kind):
        seller = seller_for(request.user)
        rows = seller_orders(seller, kind)
        if request.query_params.get("order_id"):
            order_id = serializers.IntegerField(min_value=1).run_validation(request.query_params["order_id"])
            rows = rows.filter(**{"order_id" if kind == "shop" else "pk": order_id})
        if request.query_params.get("active") == "1":
            rows = rows.exclude(**{"fulfillment_status__in" if kind == "shop" else "status__in": ["delivered", "cancelled"]})
            if kind == "shop":
                rows = rows.exclude(order__status__in=["Cancelled", "Returned", "Delivered"])
        if kind == "shop" and request.query_params.get("grouped") == "1":
            orders = Order.objects.filter(pk__in=rows.values("order_id")).order_by("-created_at", "-pk")
            def summary(order):
                lines = list(seller_orders(seller, kind).filter(order=order))
                data = order_data(lines[0], kind)
                data["id"] = order.pk
                data["items"] = [item for line in lines for item in order_data(line, kind)["items"]]
                data["amount"] = str(sum((line.seller_total for line in lines), Decimal("0")))
                statuses = {line.fulfillment_status for line in lines}
                data["status"] = statuses.pop() if len(statuses) == 1 else "partially_fulfilled"
                return data
            return page(request, orders, summary)
        return page(request, rows, lambda row: order_data(row, kind))


class SellerOrderUpdateView(SellerKindView):
    def get(self, request, kind, pk):
        row = get_object_or_404(seller_orders(seller_for(request.user), kind), pk=pk)
        return Response(order_data(row, kind))

    @transaction.atomic
    def patch(self, request, kind, pk):
        row = get_object_or_404(seller_orders(seller_for(request.user), kind).select_for_update(), pk=pk)
        target = request.data.get("status")
        if target != order_next(row, kind) or not target:
            raise ValidationError("This order cannot move to that status. Refresh the order.")
        if kind == "shop":
            if target == "shipped":
                courier = serializers.CharField(max_length=80).run_validation(request.data.get("courier", ""))
                tracking = serializers.CharField(max_length=100).run_validation(request.data.get("tracking_number", ""))
                row.seller_courier, row.seller_tracking_number = courier, tracking
            row.fulfillment_status = target
            row.save(update_fields=["fulfillment_status", "seller_courier", "seller_tracking_number"])
        else:
            row.status = target
            row.save(update_fields=["status", "updated_at"])
            if target == "ready":
                from delivery.services import ensure_food_delivery, ensure_grocery_delivery
                delivery = (ensure_food_delivery if kind == "food" else ensure_grocery_delivery)(row)
                if delivery is None:
                    raise ValidationError("Cannot dispatch this order. Check pickup and delivery GPS locations, pincode, and payment before marking it ready.")
        return Response(order_data(row, kind))


class SellerOrderCancelView(SellerKindView):
    def post(self, request, kind, pk):
        from .models import SellerCase
        from .case_services import prepare_case, submit_case_refund

        reason = serializers.CharField(min_length=5, max_length=1000).run_validation(request.data.get("reason"))
        seller = seller_for(request.user)
        with transaction.atomic():
            row = get_object_or_404(seller_orders(seller, kind).select_for_update(), pk=pk)
            order = row.order if kind == "shop" else row
            case = SellerCase.objects.filter(
                seller=seller, order_kind=kind, order_id=order.pk,
                order_item_id=row.pk if kind == "shop" else None, kind="cancellation",
            ).filter(Q(executed_at__isnull=False) | Q(status__in=["open", "reviewing"])).order_by("-pk").first()
            if case is None:
                case = SellerCase.objects.create(seller=seller, order_kind=kind, order_id=order.pk,
                    order_item_id=row.pk if kind == "shop" else None, kind="cancellation", reason=reason)
            case = prepare_case(case.pk)
        # Cancellation/refund intent is committed before contacting the provider.
        message = "Order item cancelled." if kind == "shop" else "Order cancelled."
        try:
            submit_case_refund(case)
        except ValidationError:
            message += " Refund confirmation is pending. Operations can reconcile the existing refund request."
        else:
            if case.refund_id:
                message += " Refund requested; check its status in the request history."
        row = seller_orders(seller, kind).get(pk=pk)
        return Response({"order": order_data(row, kind), "message": message})


def catalog(seller, kind):
    if kind == "shop":
        return Product.objects.filter(seller=seller).prefetch_related("variants__color").order_by("-pk")
    if kind == "food":
        return MenuItem.objects.filter(restaurant__seller=seller).prefetch_related("options").order_by("-pk")
    if kind == "grocery":
        return GroceryProduct.objects.filter(store__seller=seller).order_by("-pk")
    raise ValidationError("Unknown catalog type.")


def catalog_data(row, kind):
    result = {"id": row.pk, "name": row.name,
              "active": row.is_available if kind == "food" else row.is_active,
              "moderation": row.moderation_status if kind == "shop" else None,
              "rejection_reason": row.rejection_reason if kind == "shop" else "", "variants": []}
    if kind == "shop":
        result["variants"] = [{"id": v.pk, "name": f"{v.color.name if v.color_id else ''} / {v.size}",
                              "stock": v.stock, "price": str(v.seller_price)} for v in row.variants.all()]
    elif kind == "grocery":
        result["variants"] = [{"id": row.pk, "name": row.unit, "stock": row.stock, "price": str(row.price)}]
    else:
        result["variants"] = [{"id": v.pk, "name": v.name, "stock": None, "price": str(v.price)} for v in row.options.all()]
    return result


class SellerCatalogView(SellerKindView):
    def get(self, request, kind):
        return page(request, catalog(seller_for(request.user), kind), lambda row: catalog_data(row, kind))


class SellerCatalogUpdateView(SellerKindView):
    @transaction.atomic
    def patch(self, request, kind, pk):
        row = get_object_or_404(catalog(seller_for(request.user), kind).select_for_update(), pk=pk)
        if "active" in request.data:
            active = request.data["active"]
            if not isinstance(active, bool):
                raise ValidationError("active must be true or false.")
            if kind == "shop" and active and row.moderation_status != Product.MODERATION_APPROVED:
                raise ValidationError("Only approved listings can be published.")
            field = "is_available" if kind == "food" else "is_active"
            setattr(row, field, active)
            row.save(update_fields=[field])
        if "stock" in request.data:
            stock = serializers.IntegerField(min_value=0, max_value=1000000).run_validation(request.data["stock"])
            if kind == "shop":
                variant = get_object_or_404(ProductVariant.objects.select_for_update(), product=row, pk=request.data.get("variant_id"))
                variant.stock = stock
                variant.save(update_fields=["stock"])
                row.stock = row.variants.aggregate(total=Sum("stock"))["total"] or 0
            elif kind == "grocery":
                row.stock = stock
            else:
                raise ValidationError("Use menu availability for food items.")
            row.save(update_fields=["stock"])
        row = catalog(seller_for(request.user), kind).get(pk=pk)
        return Response(catalog_data(row, kind))


class SellerPayoutsView(SellerKindView):
    def get(self, request, kind):
        seller = seller_for(request.user)
        model = {"shop": SellerSettlement, "food": FoodSellerSettlement, "grocery": GrocerySellerSettlement}.get(kind)
        if model is None:
            raise ValidationError("Unknown payout type.")
        return page(request, model.objects.filter(seller=seller).order_by("-pk"), lambda row: {
            "id": row.pk, "order_id": row.order_id, "status": row.status,
            "amount": str(row.payout_amount), "scheduled_for": row.scheduled_for,
            "failure_reason": row.failure_reason,
        })


def delivery_data(row, agent, reveal=True):
    assigned = row.agent_id == agent.pk
    order = row.source_order
    return {"id": row.pk, "kind": row.order_kind, "status": row.status,
            "pickup_name": row.pickup_name, "pickup_address": row.pickup_address,
            "pincode": row.pincode,
            "customer_name": row.customer_name if assigned and reveal else "",
            "customer_phone": row.customer_phone if assigned and reveal else "",
            "delivery_address": row.delivery_address if assigned and reveal else "",
            "payment_method": order.payment_method,
            "collection_amount": str(row.collection_amount) if order.payment_method == "cod" else "0.00",
            "gross": str(row.agent_earning), "fee": str(row.agent_platform_fee), "net": str(row.agent_net_earning),
            "location_updated_at": row.location_updated_at,
            "next_status": {"assigned": "accepted", "accepted": "picked_up", "picked_up": "out_for_delivery"}.get(row.status)}


class RiderOnlineView(PartnerView):
    @transaction.atomic
    def patch(self, request):
        agent = get_object_or_404(DeliveryAgentProfile.objects.select_for_update(), pk=agent_for(request.user).pk)
        value = request.data.get("is_online")
        if not isinstance(value, bool):
            raise ValidationError("is_online must be true or false.")
        agent.is_online = value
        agent.save(update_fields=["is_online", "updated_at"])
        return Response({"is_online": value})


class RiderJobsView(PartnerView):
    def get(self, request):
        agent = agent_for(request.user)
        scope = request.query_params.get("scope", "active")
        rows = LocalDelivery.objects.select_related("food_order", "grocery_order", "parcel_order").order_by("-created_at", "-pk")
        if request.query_params.get("delivery_id"):
            pk = serializers.IntegerField(min_value=1).run_validation(request.query_params["delivery_id"])
            rows = rows.filter(pk=pk).filter(Q(agent=agent) | Q(agent__isnull=True, status="available", pincode=agent.pincode))
            return page(request, rows, lambda row: delivery_data(row, agent, reveal=row.status not in {"delivered", "cancelled"}))
        if scope == "available":
            rows = rows.filter(pincode=agent.pincode, agent__isnull=True, status="available") if agent.can_deliver else rows.none()
        elif scope == "history":
            rows = rows.filter(agent=agent, status__in=["delivered", "cancelled"])
        elif scope == "active":
            rows = rows.filter(agent=agent).exclude(status__in=["delivered", "cancelled"])
        else:
            raise ValidationError("Unknown jobs list.")
        return page(request, rows, lambda row: delivery_data(row, agent, reveal=scope != "history"))


class RiderAcceptView(PartnerView):
    @transaction.atomic
    def post(self, request, pk):
        agent = get_object_or_404(DeliveryAgentProfile.objects.select_for_update(), pk=agent_for(request.user).pk)
        if not agent.can_deliver:
            raise PermissionDenied("Go online before accepting deliveries.")
        row = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=pk, pincode=agent.pincode)
        if row.agent_id == agent.pk and row.status == "assigned":
            return Response(delivery_data(row, agent))
        if row.agent_id or row.status != "available":
            return Response({"message": "This delivery is no longer available."}, status=409)
        order = row.source_order
        if order.status.lower() in {"cancelled", "returned"} or (order.payment_method != "cod" and order.payment_status != "Paid"):
            raise ValidationError("This order is not ready for delivery.")
        row.agent, row.status, row.assigned_at = agent, "assigned", timezone.now()
        row.save(update_fields=["agent", "status", "assigned_at", "updated_at"])
        return Response(delivery_data(row, agent))


class RiderStatusView(PartnerView):
    @transaction.atomic
    def patch(self, request, pk):
        agent = agent_for(request.user)
        row = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=pk, agent=agent)
        target = request.data.get("status")
        if target != {"assigned": "accepted", "accepted": "picked_up", "picked_up": "out_for_delivery"}.get(row.status) or not target:
            raise ValidationError("This delivery cannot move to that status. Refresh the job.")
        if row.source_order.status.lower() in {"cancelled", "returned"}:
            raise ValidationError("This order was cancelled.")
        row.status = target
        if target == "picked_up":
            row.picked_up_at = timezone.now()
            issue_delivery_otp(row)
        row.save(update_fields=["status", "picked_up_at", "updated_at"])
        return Response(delivery_data(row, agent))


class RiderCompleteView(PartnerView):
    throttle_classes = [OTPThrottle]

    @transaction.atomic
    def post(self, request, pk):
        agent = agent_for(request.user)
        row = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=pk, agent=agent)
        if row.status == "delivered":
            return Response({"message": "Delivery already completed."})
        if row.status != "out_for_delivery" or row.source_order.status.lower() in {"cancelled", "returned"}:
            raise ValidationError("The order must be out for delivery first.")
        otp = serializers.RegexField(r"^\d{6}$").run_validation(request.data.get("otp", ""))
        if not otp_is_valid(row, otp):
            raise ValidationError("The delivery OTP is incorrect or expired.")
        if row.source_order.payment_method == "cod" and request.data.get("cash_collected") is not True:
            raise ValidationError("Confirm that the cash shown on this job has been collected.")
        complete_delivery(row, agent)
        return Response({"message": "Delivery completed. Your earning has been recorded."})


class LocationInput(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=Decimal("-90"), max_value=Decimal("90"))
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=Decimal("-180"), max_value=Decimal("180"))
    accuracy = serializers.IntegerField(min_value=0, max_value=100000)


class RiderLocationView(PartnerView):
    @transaction.atomic
    def post(self, request, pk):
        row = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=pk, agent=agent_for(request.user))
        if row.status not in {"accepted", "picked_up", "out_for_delivery"}:
            raise ValidationError("Location sharing is only available during an active delivery.")
        data = LocationInput(data=request.data)
        data.is_valid(raise_exception=True)
        row.agent_latitude = data.validated_data["latitude"]
        row.agent_longitude = data.validated_data["longitude"]
        row.location_accuracy_meters = data.validated_data["accuracy"]
        row.location_updated_at = timezone.now()
        row.save(update_fields=["agent_latitude", "agent_longitude", "location_accuracy_meters", "location_updated_at"])
        return Response({"location_updated_at": row.location_updated_at})


class RiderEarningsView(PartnerView):
    def get(self, request):
        agent = agent_for(request.user)
        return page(request, agent.earnings.order_by("-created_at", "-pk"), lambda row: {
            "id": row.pk, "delivery_id": row.delivery_id, "gross": str(row.amount),
            "fee": str(row.platform_fee_amount), "amount": str(row.net_amount),
            "status": row.status, "scheduled_for": row.scheduled_for, "failure_reason": row.failure_reason,
        })
