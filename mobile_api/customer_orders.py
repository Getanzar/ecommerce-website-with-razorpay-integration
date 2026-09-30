"""Customer post-purchase actions, shared with marketplace operations."""
from types import SimpleNamespace
from xml.sax.saxutils import escape

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from delivery.models import LocalDelivery
from orders.models import Order, OrderItem, ReturnRequest
from products.models import ProductReview
from .views import _owned_order


class CustomerActionThrottle(UserRateThrottle):
    scope = "customer_order_actions"
    rate = "60/min"


class CustomerView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [CustomerActionThrottle]


def owned(request, kind, pk):
    if kind not in {"shop", "food", "grocery"}:
        raise ValidationError("Unknown order type.")
    return _owned_order(request.user, kind, pk)


def review_data(row):
    return {"rating": row.rating, "title": row.title, "review": row.review,
            "approved": row.is_approved, "updated_at": row.updated_at}


class ReviewInput(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=100, allow_blank=True, default="")
    review = serializers.CharField(min_length=5, max_length=5000)


class ItemReviewView(CustomerView):
    def item(self, request, pk):
        return get_object_or_404(OrderItem.objects.select_related("order"), pk=pk, order__user=request.user)

    def get(self, request, pk):
        item = self.item(request, pk)
        row = ProductReview.objects.filter(user=request.user, product_id=item.product_id).first()
        return Response({"review": review_data(row) if row else None})

    @transaction.atomic
    def post(self, request, pk):
        item = self.item(request, pk)
        if item.order.status != "Delivered" and item.fulfillment_status != "delivered":
            raise ValidationError("You can review a product after receiving it.")
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        # Serialize repeat submissions across separate order items of the same product.
        from django.contrib.auth.models import User
        User.objects.select_for_update().get(pk=request.user.pk)
        row, _ = ProductReview.objects.update_or_create(
            user=request.user, product_id=item.product_id,
            defaults={**data.validated_data, "is_verified_purchase": True, "is_approved": False},
        )
        return Response({"message": "Review submitted for moderation.", "review": review_data(row)})


class ReturnInput(serializers.Serializer):
    order_item_id = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=ReturnRequest.REASON_CHOICES)
    description = serializers.CharField(min_length=5, max_length=5000)
    image = serializers.ImageField(required=False)

    def validate_image(self, value):
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Choose an image smaller than 8 MB.")
        return value


def return_data(row):
    return {"id": row.pk, "order_item_id": row.order_item_id, "reason": row.reason,
            "description": row.description, "status": row.status,
            "refund_status": row.refund_status, "created_at": row.created_at,
            "updated_at": row.updated_at}


class OrderReturnsView(CustomerView):
    @transaction.atomic
    def post(self, request, pk):
        order = get_object_or_404(Order.objects.select_for_update(), pk=pk, user=request.user)
        if not order.can_request_return:
            raise ValidationError("This order is outside its return window or has not been delivered.")
        data = ReturnInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        item = get_object_or_404(OrderItem, pk=values.pop("order_item_id"), order=order)
        if item.fulfillment_status == "cancelled":
            raise ValidationError("Cancelled items cannot be returned.")
        if order.return_requests.filter(Q(order_item=item) | Q(order_item__isnull=True)).exists():
            return Response({"message": "A return request already exists for this item."}, status=409)
        row = ReturnRequest.objects.create(order=order, order_item=item, user=request.user, **values)
        return Response(return_data(row), status=201)


class OrderExperienceView(CustomerView):
    def get(self, request, kind, pk):
        order = owned(request, kind, pk)
        link = {"shop": "parcel_order", "food": "food_order", "grocery": "grocery_order"}[kind]
        deliveries = LocalDelivery.objects.filter(**{link: order}).select_related("parcel_seller")
        shipments = [{"id": f"local-{row.pk}", "seller": row.pickup_name, "provider": "Local delivery",
                      "status": row.status, "tracking_number": "", "location_updated_at": row.location_updated_at,
                      "latitude": row.agent_latitude, "longitude": row.agent_longitude} for row in deliveries]
        if kind == "shop":
            shipments += [{"id": f"carrier-{row.pk}", "seller": row.seller.store_name if row.seller else "ZIYAMART",
                           "provider": "Delhivery", "status": row.carrier_status, "tracking_number": row.awb_number,
                           "location_updated_at": None, "latitude": None, "longitude": None}
                          for row in order.sellerdeliverycharges.filter(provider="delhivery").select_related("seller")]
        items = []
        if kind == "shop":
            reviews = {r.product_id: r for r in ProductReview.objects.filter(user=request.user, product_id__in=order.items.values("product_id"))}
            for item in order.items.all():
                items.append({"id": item.pk, "name": item.product_name, "quantity": item.quantity,
                              "can_review": order.status == "Delivered" or item.fulfillment_status == "delivered",
                              "can_return": order.can_request_return and item.fulfillment_status != "cancelled" and not order.return_requests.filter(Q(order_item=item) | Q(order_item__isnull=True)).exists(),
                              "review": review_data(reviews[item.product_id]) if item.product_id in reviews else None})
        return Response({"items": items, "shipments": shipments,
                         "returns": [return_data(r) for r in order.return_requests.all()] if kind == "shop" else [],
                         "return_reasons": [value for value, _ in ReturnRequest.REASON_CHOICES],
                         "return_deadline": order.return_deadline if kind == "shop" else None,
                         "invoice_available": order.status.lower() != "cancelled" and (order.payment_status == "Paid" or order.status.lower() == "delivered")})


class OrderInvoiceView(CustomerView):
    def get(self, request, kind, pk):
        order = owned(request, kind, pk)
        if order.status.lower() == "cancelled" or (order.payment_status != "Paid" and order.status.lower() != "delivered"):
            raise ValidationError("An invoice becomes available after payment or delivery.")
        from orders.invoice import generate_invoice
        # Reuse the existing invoice layout while adapting each commerce channel.
        items = [SimpleNamespace(
            product_name=row.product_name if kind != "food" else row.item_name,
            quantity=row.quantity, price=row.price if kind == "shop" else row.unit_price,
            subtotal=row.subtotal if kind == "shop" else row.line_total if kind == "food" else row.total,
        ) for row in order.items.all()]
        adapter = SimpleNamespace(id=f"{kind.upper()}-{order.pk}", full_name=escape(order.full_name),
                                  phone=escape(order.phone), payment_method=escape(order.payment_method),
                                  status=escape(order.status), total_price=order.total_price if kind == "shop" else order.total,
                                  items=SimpleNamespace(all=lambda: items), chargebreakdowns=order.chargebreakdowns)
        response = HttpResponse(generate_invoice(adapter), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="ZIYAMART-{kind}-{order.pk}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
