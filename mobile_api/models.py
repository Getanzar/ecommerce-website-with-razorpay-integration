from django.conf import settings
from django.db import models
import uuid
from .storage import PrivateEvidenceStorage


class CustomerCareRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="mobile_care_requests", on_delete=models.CASCADE)
    order_kind = models.CharField(max_length=12, choices=(("shop", "Shop"), ("food", "Food"), ("grocery", "Grocery")))
    order_id = models.PositiveIntegerField(blank=True, null=True)
    order_item_id = models.PositiveIntegerField(blank=True, null=True)
    request_type = models.CharField(max_length=12, choices=(("return", "Return"), ("support", "Support")))
    reason = models.CharField(max_length=100)
    message = models.TextField(blank=True)
    attachment = models.ImageField(upload_to="customer-care/", blank=True, null=True)
    status = models.CharField(max_length=20, default="Open")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("user", "order_kind", "order_id", "request_type"), condition=models.Q(order_id__isnull=False), name="one_open_mobile_request_per_order_type")]


class CustomerCareReply(models.Model):
    request = models.ForeignKey(CustomerCareRequest, related_name="replies", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    attachment = models.ImageField(upload_to="customer-care/replies/", blank=True, null=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class CheckoutSession(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="mobile_checkout_sessions", on_delete=models.CASCADE)
    order_kind = models.CharField(max_length=12, choices=(("shop", "Shop"), ("food", "Food"), ("grocery", "Grocery")))
    address_id = models.PositiveIntegerField()
    cart_fingerprint = models.CharField(max_length=64)
    quote = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, default="quoted")
    order_id = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "order_kind", "idempotency_key"), condition=~models.Q(idempotency_key=""), name="unique_mobile_checkout_submission")]


class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="mobile_notification_preferences", on_delete=models.CASCADE)
    order_updates = models.BooleanField(default=True)
    payment_updates = models.BooleanField(default=True)
    promotions = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class PushDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="mobile_push_devices", on_delete=models.CASCADE)
    expo_push_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, blank=True)
    active = models.BooleanField(default=True)
    session = models.ForeignKey("DeviceSession", null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)


class AccountDeletionRequest(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="deletion_request", on_delete=models.CASCADE)
    reason = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)


class DeviceSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    device_name = models.CharField(max_length=120, default="Mobile device")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500)
    data = models.JSONField(default=dict)
    category = models.CharField(max_length=30, default="order_updates")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    push_status = models.CharField(max_length=20, default="pending")
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-id",)


class PushReceipt(models.Model):
    ticket_id = models.CharField(max_length=100, unique=True)
    device = models.ForeignKey(PushDevice, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default="pending")
    error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DeliveryEvidence(models.Model):
    delivery = models.ForeignKey("delivery.LocalDelivery", related_name="mobile_evidence", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=(("photo", "Photo"), ("failure", "Failure"), ("dispatch", "Dispatch")))
    photo = models.ImageField(upload_to="delivery/proof/", blank=True, storage=PrivateEvidenceStorage())
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SellerCase(models.Model):
    seller = models.ForeignKey("accounts.SellerProfile", on_delete=models.PROTECT)
    order_kind = models.CharField(max_length=12)
    order_id = models.PositiveIntegerField()
    order_item_id = models.PositiveIntegerField(null=True, blank=True)
    kind = models.CharField(max_length=20, choices=(("cancellation", "Cancellation"), ("refund", "Refund"), ("dispute", "Dispute")))
    reason = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, default="open", choices=(("open", "Open"), ("reviewing", "Reviewing"), ("resolved", "Resolved"), ("rejected", "Rejected")))
    resolution = models.TextField(blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    refund = models.OneToOneField("payments.RefundTransaction", null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("seller", "order_kind", "order_id", "order_item_id", "kind"), condition=models.Q(status__in=("open", "reviewing"), order_item_id__isnull=False), name="one_active_seller_item_case"),
            models.UniqueConstraint(fields=("seller", "order_kind", "order_id", "kind"), condition=models.Q(status__in=("open", "reviewing"), order_item_id__isnull=True), name="one_active_seller_order_case"),
        ]
