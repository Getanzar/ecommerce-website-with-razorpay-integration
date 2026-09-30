from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from delivery.models import LocalDelivery
from .models import DeviceSession, Notification, DeliveryEvidence, SellerCase
from .partners import PartnerView, agent_for, seller_for, seller_orders


class SessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = DeviceSession.objects.filter(user=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now())
        return Response([{"id": row.pk, "device_name": row.device_name, "created_at": row.created_at,
                          "last_seen_at": row.last_seen_at, "current": isinstance(request.auth, DeviceSession) and row.pk == request.auth.pk} for row in rows])

    def delete(self, request, pk):
        row = get_object_or_404(DeviceSession, user=request.user, pk=pk)
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        from .models import PushDevice
        PushDevice.objects.filter(session=row).update(active=False)
        return Response(status=204)


class InboxView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = Notification.objects.filter(user=request.user)
        before = request.query_params.get("before")
        if before:
            before = serializers.IntegerField(min_value=1).run_validation(before)
            rows = rows.filter(pk__lt=before)
        return Response(list(rows.values("id", "title", "body", "data", "read_at", "created_at")[:50]))

    def patch(self, request, pk):
        row = get_object_or_404(Notification, user=request.user, pk=pk)
        row.read_at = timezone.now()
        row.save(update_fields=["read_at"])
        return Response({"read_at": row.read_at})


class EvidenceInput(serializers.Serializer):
    photo = serializers.ImageField(required=False)
    reason = serializers.ChoiceField(choices=["customer_unavailable", "incorrect_address", "customer_refused", "unsafe_location", "vehicle_breakdown"], required=False)

    def validate_photo(self, value):
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError("Photo must be under 8 MB.")
        from io import BytesIO
        from PIL import Image, ImageOps
        from django.core.files.base import ContentFile
        with Image.open(value) as image:
            if image.width * image.height > 25000000:
                raise serializers.ValidationError("Photo resolution is too large.")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2048, 2048))
            output = BytesIO()
            image.save(output, format="JPEG", quality=85)
        # Strip metadata and standardize the private download's media type.
        return ContentFile(output.getvalue(), name="proof.jpg")


class RiderEvidenceView(PartnerView):
    @transaction.atomic
    def post(self, request, pk):
        row = get_object_or_404(LocalDelivery.objects.select_for_update(), pk=pk, agent=agent_for(request.user))
        if row.status not in {"accepted", "picked_up", "out_for_delivery"}:
            raise serializers.ValidationError("Evidence requires an active delivery.")
        data = EvidenceInput(data=request.data)
        data.is_valid(raise_exception=True)
        photo, reason = data.validated_data.get("photo"), data.validated_data.get("reason")
        if not photo and not reason:
            raise serializers.ValidationError("Choose a photo or a failed delivery reason.")
        evidence = DeliveryEvidence.objects.create(delivery=row, actor=request.user, kind="photo" if photo else "failure", photo=photo or "", reason=reason or "")
        # Failure is an exception for dispatch to resolve, never proof of completion.
        return Response({"id": evidence.pk, "status": "recorded"}, status=201)


class SellerCasesView(PartnerView):
    def get(self, request, kind, pk):
        seller = seller_for(request.user)
        row = get_object_or_404(seller_orders(seller, kind), pk=pk)
        order_id = row.order_id if kind == "shop" else row.pk
        return Response(list(SellerCase.objects.filter(seller=seller, order_kind=kind, order_id=order_id, order_item_id=row.pk if kind == "shop" else None).values("id", "kind", "reason", "status", "resolution", "created_at")))

    @transaction.atomic
    def post(self, request, kind, pk):
        seller = seller_for(request.user)
        row = get_object_or_404(seller_orders(seller, kind).select_for_update(), pk=pk)
        case_kind = serializers.ChoiceField(choices=["cancellation", "refund", "dispute"]).run_validation(request.data.get("kind"))
        reason = serializers.CharField(min_length=5, max_length=1000).run_validation(request.data.get("reason"))
        order = row.order if kind == "shop" else row
        if case_kind == "cancellation" and order.status.lower() in {"delivered", "cancelled", "returned"}:
            raise serializers.ValidationError("This order cannot be cancelled.")
        if case_kind == "refund" and order.payment_status != "Paid":
            raise serializers.ValidationError("Only a paid order can have a refund review.")
        case, created = SellerCase.objects.get_or_create(seller=seller, order_kind=kind, order_id=order.pk,
            order_item_id=row.pk if kind == "shop" else None, kind=case_kind, status__in=["open", "reviewing"], defaults={"reason": reason})
        return Response({"id": case.pk, "status": case.status}, status=201 if created else 200)
