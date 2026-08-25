import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


PINCODE_VALIDATOR = RegexValidator(r"^\d{6}$", "Enter a valid 6-digit pincode.")


class DeliveryZone(models.Model):
    pincode = models.CharField(max_length=6, unique=True, validators=[PINCODE_VALIDATOR])
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("pincode",)

    def __str__(self):
        return f"{self.pincode} - {self.city}"


class DeliveryAgentProfile(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending verification"),
        ("approved", "Approved"),
        ("suspended", "Suspended"),
        ("rejected", "Rejected"),
    )
    VEHICLE_CHOICES = (
        ("bicycle", "Bicycle"),
        ("motorcycle", "Motorcycle/Scooter"),
        ("ev", "Electric vehicle"),
        ("other", "Other"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="delivery_agent", on_delete=models.CASCADE
    )
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6, db_index=True, validators=[PINCODE_VALIDATOR])
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES)
    vehicle_number = models.CharField(max_length=30, blank=True)
    aadhaar_last4 = models.CharField(max_length=4)
    driving_license_number = models.CharField(max_length=40, blank=True)
    id_document = models.ImageField(upload_to="delivery/identity/", blank=True, null=True)
    driving_license_image = models.ImageField(upload_to="delivery/licenses/", blank=True, null=True)
    bank_account_holder = models.CharField(max_length=120, blank=True)
    bank_account_last4 = models.CharField(max_length=4, blank=True)
    bank_ifsc_code = models.CharField(max_length=11, blank=True)
    razorpay_contact_id = models.CharField(max_length=100, blank=True)
    razorpay_fund_account_id = models.CharField(max_length=100, blank=True)
    payouts_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    is_online = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)

    @property
    def can_deliver(self):
        return self.status == "approved" and self.is_online

    def __str__(self):
        return f"{self.full_name} ({self.pincode})"


class LocalDelivery(models.Model):
    STATUS_CHOICES = (
        ("available", "Available"),
        ("assigned", "Assigned"),
        ("accepted", "Accepted"),
        ("picked_up", "Picked up"),
        ("out_for_delivery", "Out for delivery"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    grocery_order = models.OneToOneField(
        "groceries.GroceryOrder", related_name="local_delivery", null=True, blank=True,
        on_delete=models.PROTECT,
    )
    food_order = models.OneToOneField(
        "food.FoodOrder", related_name="local_delivery", null=True, blank=True,
        on_delete=models.PROTECT,
    )
    parcel_order = models.ForeignKey(
        "orders.Order", related_name="local_deliveries", null=True, blank=True,
        on_delete=models.PROTECT,
    )
    parcel_seller = models.ForeignKey(
        "accounts.SellerProfile", related_name="local_parcel_deliveries", null=True, blank=True,
        on_delete=models.PROTECT,
    )
    agent = models.ForeignKey(
        DeliveryAgentProfile, related_name="deliveries", null=True, blank=True,
        on_delete=models.PROTECT,
    )
    pincode = models.CharField(max_length=6, db_index=True, validators=[PINCODE_VALIDATOR])
    pickup_name = models.CharField(max_length=150)
    pickup_address = models.TextField()
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=15)
    delivery_address = models.TextField()
    customer_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    customer_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    agent_earning = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    collection_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="available")
    delivery_otp_hash = models.CharField(max_length=128, blank=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    assigned_at = models.DateTimeField(blank=True, null=True)
    picked_up_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    agent_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    agent_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    location_accuracy_meters = models.PositiveIntegerField(blank=True, null=True)
    location_updated_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(grocery_order__isnull=False, food_order__isnull=True, parcel_order__isnull=True) |
                    models.Q(grocery_order__isnull=True, food_order__isnull=False, parcel_order__isnull=True) |
                    models.Q(grocery_order__isnull=True, food_order__isnull=True, parcel_order__isnull=False, parcel_seller__isnull=False)
                ),
                name="delivery_exactly_one_order",
            ),
            models.UniqueConstraint(
                fields=("parcel_order", "parcel_seller"),
                condition=models.Q(parcel_order__isnull=False),
                name="one_local_delivery_per_parcel_seller",
            ),
        ]

    @property
    def source_order(self):
        return self.grocery_order or self.food_order or self.parcel_order

    @property
    def order_kind(self):
        if self.grocery_order_id:
            return "Grocery"
        return "Food" if self.food_order_id else "Parcel"

    @property
    def agent_platform_fee(self):
        rate = Decimal(str(getattr(settings, "DELIVERY_AGENT_PLATFORM_FEE_PERCENT", "10.00")))
        return (self.agent_earning * rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def agent_net_earning(self):
        return self.agent_earning - self.agent_platform_fee

    def __str__(self):
        return f"{self.order_kind} delivery #{self.pk} - {self.pincode}"


class DeliveryEarning(models.Model):
    STATUS_CHOICES = (("pending", "Pending COD remittance"), ("payable", "Payable"), ("processing", "Processing"), ("paid", "Paid"), ("failed", "Failed"))
    agent = models.ForeignKey(DeliveryAgentProfile, related_name="earnings", on_delete=models.PROTECT)
    delivery = models.OneToOneField(LocalDelivery, related_name="earning", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    platform_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    platform_fee_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="payable")
    paid_at = models.DateTimeField(blank=True, null=True)
    scheduled_for = models.DateTimeField(blank=True, null=True)
    provider_payout_id = models.CharField(max_length=100, blank=True)
    payout_idempotency_key = models.CharField(max_length=36, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        percent = Decimal(str(getattr(settings, "DELIVERY_AGENT_PLATFORM_FEE_PERCENT", "10.00")))
        self.platform_fee_percent = percent
        self.platform_fee_amount = (self.amount * percent / Decimal("100")).quantize(Decimal("0.01"))
        self.net_amount = self.amount - self.platform_fee_amount
        if not self.payout_idempotency_key:
            self.payout_idempotency_key = str(uuid.uuid4())
        super().save(*args, **kwargs)
