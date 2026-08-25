import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


ZERO = Decimal("0.00")


class OrderLinkMixin(models.Model):
    parcel_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.PROTECT,
        related_name="%(class)ss",
    )
    food_order = models.ForeignKey(
        "food.FoodOrder", null=True, blank=True, on_delete=models.PROTECT,
        related_name="%(class)ss",
    )
    grocery_order = models.ForeignKey(
        "groceries.GroceryOrder", null=True, blank=True, on_delete=models.PROTECT,
        related_name="%(class)ss",
    )

    class Meta:
        abstract = True

    @property
    def order(self):
        return self.parcel_order or self.food_order or self.grocery_order

    @property
    def channel(self):
        if self.parcel_order_id:
            return "parcel"
        return "food" if self.food_order_id else "grocery"


class ChargeBreakdown(OrderLinkMixin):
    merchant_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    merchandise_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_fee_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    seller_sponsored_delivery = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customer_delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_mode = models.CharField(max_length=20, choices=(("local", "Local"), ("delhivery", "Delhivery"), ("mixed", "Mixed")))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(parcel_order__isnull=False, food_order__isnull=True, grocery_order__isnull=True)
                    | Q(parcel_order__isnull=True, food_order__isnull=False, grocery_order__isnull=True)
                    | Q(parcel_order__isnull=True, food_order__isnull=True, grocery_order__isnull=False)
                ),
                name="charge_breakdown_exactly_one_order",
            ),
            models.UniqueConstraint(fields=("parcel_order",), condition=Q(parcel_order__isnull=False), name="one_breakdown_per_parcel"),
            models.UniqueConstraint(fields=("food_order",), condition=Q(food_order__isnull=False), name="one_breakdown_per_food"),
            models.UniqueConstraint(fields=("grocery_order",), condition=Q(grocery_order__isnull=False), name="one_breakdown_per_grocery"),
        ]

    @property
    def total_gst(self):
        return self.merchandise_gst + self.platform_fee_gst + self.delivery_gst


class PaymentTransaction(OrderLinkMixin):
    STATUS_CHOICES = (
        ("created", "Created"), ("authorized", "Authorized"),
        ("captured", "Captured"), ("failed", "Failed"),
        ("partially_refunded", "Partially refunded"), ("refunded", "Refunded"),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="payment_transactions", on_delete=models.PROTECT)
    channel_name = models.CharField(max_length=20, choices=(("parcel", "Parcel"), ("food", "Food"), ("grocery", "Grocery")))
    provider = models.CharField(max_length=20, choices=(("razorpay", "Razorpay"), ("cod", "Cash on delivery")))
    provider_order_id = models.CharField(max_length=120, blank=True, db_index=True)
    provider_payment_id = models.CharField(max_length=120, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="created")
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    snapshot = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)
    captured_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("provider_order_id",), condition=~Q(provider_order_id=""), name="unique_payment_provider_order"),
            models.UniqueConstraint(fields=("provider_payment_id",), condition=~Q(provider_payment_id=""), name="unique_payment_provider_payment"),
        ]


class PaymentWebhookEvent(models.Model):
    provider = models.CharField(max_length=20, default="razorpay")
    event_id = models.CharField(max_length=150)
    event_type = models.CharField(max_length=80)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=(("received", "Received"), ("processed", "Processed"), ("ignored", "Ignored"), ("failed", "Failed")), default="received")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "event_id"), name="unique_payment_webhook_event",
            ),
        ]


class RefundTransaction(OrderLinkMixin):
    STATUS_CHOICES = (("requested", "Requested"), ("processing", "Processing"), ("processed", "Processed"), ("failed", "Failed"))
    payment = models.ForeignKey(PaymentTransaction, related_name="refunds", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    provider_refund_id = models.CharField(max_length=120, blank=True, db_index=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("provider_refund_id",), condition=~Q(provider_refund_id=""), name="unique_provider_refund"),
        ]


class SellerDeliveryCharge(OrderLinkMixin):
    STATUS_CHOICES = (("quoted", "Quoted"), ("deducted", "Deducted"), ("reconciled", "Reconciled"), ("reversed", "Reversed"))
    seller = models.ForeignKey("accounts.SellerProfile", related_name="delivery_charges", null=True, blank=True, on_delete=models.PROTECT)
    provider = models.CharField(max_length=20, choices=(("local", "Local delivery"), ("delhivery", "Delhivery")))
    origin_pincode = models.CharField(max_length=6)
    destination_pincode = models.CharField(max_length=6)
    chargeable_weight_grams = models.PositiveIntegerField(default=0)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    carrier_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    handling_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quoted_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    final_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customer_collection_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    awb_number = models.CharField(max_length=100, blank=True)
    carrier_status = models.CharField(max_length=80, blank=True)
    manifestation_payload = models.JSONField(default=dict, blank=True)
    quote_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="quoted")
    quoted_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-quoted_at",)
        constraints = [
            models.UniqueConstraint(fields=("parcel_order", "seller"), condition=Q(parcel_order__isnull=False), name="one_parcel_delivery_charge_per_seller"),
            models.UniqueConstraint(fields=("food_order", "seller"), condition=Q(food_order__isnull=False), name="one_food_delivery_charge_per_seller"),
            models.UniqueConstraint(fields=("grocery_order", "seller"), condition=Q(grocery_order__isnull=False), name="one_grocery_delivery_charge_per_seller"),
            models.UniqueConstraint(
                fields=("parcel_order",),
                condition=Q(parcel_order__isnull=False, seller__isnull=True),
                name="one_platform_parcel_delivery_charge",
            ),
        ]

    @property
    def amount_due(self):
        return self.final_total or self.quoted_total


class CODRemittance(OrderLinkMixin):
    STATUS_CHOICES = (
        ("awaiting_collection", "Awaiting carrier collection"),
        ("collected", "Collected by agent/carrier"),
        ("remitted", "Remitted to platform"),
        ("settled", "Settled"),
        ("disputed", "Disputed"),
    )
    SOURCE_CHOICES = (("local_agent", "Local delivery agent"), ("delhivery", "Delhivery"))
    delivery = models.OneToOneField("delivery.LocalDelivery", related_name="cod_remittance", null=True, blank=True, on_delete=models.PROTECT)
    agent = models.ForeignKey("delivery.DeliveryAgentProfile", related_name="cod_remittances", null=True, blank=True, on_delete=models.PROTECT)
    seller = models.ForeignKey("accounts.SellerProfile", related_name="cod_remittances", null=True, blank=True, on_delete=models.PROTECT)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="local_agent")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="collected")
    reference = models.CharField(max_length=100, blank=True)
    collected_at = models.DateTimeField(blank=True, null=True)
    remitted_at = models.DateTimeField(blank=True, null=True)
    settled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("parcel_order", "seller"),
                condition=Q(parcel_order__isnull=False, seller__isnull=False),
                name="one_cod_remittance_per_parcel_seller",
            ),
        ]
