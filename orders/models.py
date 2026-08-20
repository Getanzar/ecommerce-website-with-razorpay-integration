from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from products.models import Product, ProductVariant
from accounts.models import SellerProfile


class Order(models.Model):

    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Processing", "Processing"),
        ("Packed", "Packed"),
        ("Shipped", "Shipped"),
        ("Out for Delivery", "Out for Delivery"),
        ("Delivered", "Delivered"),
        ("Cancelled", "Cancelled"),
        ("Returned", "Returned"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("online", "Online Payment"),
        ("cod", "Cash on Delivery"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Paid", "Paid"),
        ("Failed", "Failed"),
        ("Refunded", "Refunded"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders"
    )

    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)

    address = models.TextField()
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    pincode = models.CharField(max_length=10)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="Pending"
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="online"
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="Pending"
    )
    # ---------- Admin Workflow ----------

    is_new = models.BooleanField(
        default=True
    )

    confirmed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    packed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    shipped_at = models.DateTimeField(
        blank=True,
        null=True
    )
    out_for_delivery_at = models.DateTimeField(
        blank=True,
        null=True
    )

    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_orders"
    )

    admin_note = models.TextField(
        blank=True,
        null=True
    )

    # ---------- Razorpay ----------
    razorpay_order_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    razorpay_payment_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

        # ---------- Refund ----------
    refund_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    refunded_at = models.DateTimeField(
        blank=True,
        null=True
    )

    # ---------- Shipping ----------
    courier = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    awb_number = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    delivery_status = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    eta = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    # ---------- Cancellation ----------
    cancel_reason = models.TextField(
        blank=True,
        null=True
    )

    cancelled_at = models.DateTimeField(
        blank=True,
        null=True
    )

    # ---------- Delivery ----------
    delivered_at = models.DateTimeField(
        blank=True,
        null=True
    )

    # ---------- Returns ----------
    returned_at = models.DateTimeField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"
    

class OrderItem(models.Model):

    FULFILLMENT_CHOICES = [
        ("new", "New"), ("accepted", "Accepted"), ("packed", "Packed"),
        ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled"),
    ]

    order = models.ForeignKey(
        Order,
        related_name="items",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT
    )

    variant = models.ForeignKey(
        ProductVariant,
        related_name="order_items",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # =========================
    # Product Snapshot
    # (Never changes after order)
    # =========================

    product_name = models.CharField(
        max_length=255
    )

    product_image = models.ImageField(
        upload_to="order_items/",
        blank=True,
        null=True,
    )

    product_color = models.CharField(
        max_length=50,
        blank=True,
    )

    product_size = models.CharField(
        max_length=20,
        blank=True,
    )

    # SKU snapshot
    product_sku = models.CharField(
        max_length=100,
        blank=True,
    )

    # =========================
    # Pricing
    # =========================

    quantity = models.PositiveIntegerField(
        default=1
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price per unit at the time of purchase",
    )

    # Discount applied to this item
    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    # Tax applied to this item
    tax = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    fulfillment_status = models.CharField(max_length=20, choices=FULFILLMENT_CHOICES, default="new")
    seller_tracking_number = models.CharField(max_length=100, blank=True)
    seller_courier = models.CharField(max_length=100, blank=True)
    fulfilled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["id"]

    @property
    def subtotal(self):
        return self.price * self.quantity

    @property
    def total(self):
        return (
            (self.price * self.quantity)
            - self.discount
            + self.tax
        )

    @property
    def seller_total(self):
        fee = self.product.platform_fee_percent
        return (self.total / (Decimal("1") + fee / Decimal("100"))).quantize(Decimal("0.01"))

    def __str__(self):
        return (
            f"Order #{self.order.id} - "
            f"{self.product_name} x {self.quantity}"
        )


class SellerSettlement(models.Model):
    """One immutable seller earning calculation per marketplace order."""

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("processing", "Processing"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("on_hold", "On hold"),
        ("reversed", "Reversed"),
        ("offset", "Offset against return"),
    ]

    seller = models.ForeignKey(
        SellerProfile, related_name="settlements", on_delete=models.PROTECT
    )
    order = models.ForeignKey(
        Order, related_name="seller_settlements", on_delete=models.PROTECT
    )
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deductions_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=Order.PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    scheduled_for = models.DateTimeField()
    provider_payout_id = models.CharField(max_length=100, blank=True)
    failure_reason = models.TextField(blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["seller", "order"], name="one_settlement_per_seller_order"
            )
        ]

    def __str__(self):
        return f"{self.seller} / Order #{self.order_id} / {self.net_amount}"

    @property
    def payout_amount(self):
        return max(self.net_amount - self.deductions_amount, Decimal("0.00"))

    @property
    def payout_reference_key(self):
        return f"general-{self.pk}"


class SellerReturnDebit(models.Model):
    seller = models.ForeignKey(SellerProfile, related_name="return_debits", on_delete=models.PROTECT)
    return_request = models.OneToOneField("ReturnRequest", related_name="seller_debit", on_delete=models.PROTECT)
    original_amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return #{self.return_request_id}: {self.remaining_amount} due"


class SellerNotification(models.Model):
    seller = models.ForeignKey(SellerProfile, related_name="notifications", on_delete=models.CASCADE)
    kind = models.CharField(max_length=40, default="return_balance_due")
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
    
class ReturnRequest(models.Model):

    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
        ("Completed", "Completed"),
    ]

    REASON_CHOICES = [
        ("Wrong Product", "Wrong Product"),
        ("Damaged Product", "Damaged Product"),
        ("Wrong Size", "Wrong Size"),
        ("Quality Issue", "Quality Issue"),
        ("Other", "Other"),
    ]
    REFUND_STATUS = [
        ("Pending", "Pending"),
        ("Processed", "Processed"),
        ("Rejected", "Rejected"),
    ]

    admin_note = models.TextField(
        blank=True,
        null=True,
    )

    refund_status = models.CharField(
        max_length=20,
        choices=REFUND_STATUS,
        default="Pending",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="return_requests"
    )

    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="return_requests",
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    reason = models.CharField(
        max_length=100,
        choices=REASON_CHOICES
    )

    description = models.TextField(blank=True)

    image = models.ImageField(
        upload_to="returns/",
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Pending"
    )


    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Return #{self.id} - Order {self.order.id}"
    

class SupportTicket(models.Model):

    STATUS_CHOICES = [
        ("Open", "Open"),
        ("In Progress", "In Progress"),
        ("Resolved", "Resolved"),
        ("Closed", "Closed"),
    ]

    ISSUE_CHOICES = [
        ("Order Delay", "Order Delay"),
        ("Wrong Product", "Wrong Product"),
        ("Damaged Product", "Damaged Product"),
        ("Payment Issue", "Payment Issue"),
        ("Cancellation", "Cancellation"),
        ("Return", "Return"),
        ("Refund", "Refund"),
        ("Other", "Other"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="support_tickets"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    issue = models.CharField(
        max_length=50,
        choices=ISSUE_CHOICES
    )

    message = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Open"
    )

    # NEW
    admin_note = models.TextField(
        blank=True,
        null=True
    )

    # NEW
    is_read = models.BooleanField(
        default=False
    )

    # NEW
    last_reply_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"Ticket #{self.id} - Order {self.order.id}"


class SupportReply(models.Model):

    ticket = models.ForeignKey(
        SupportTicket,
        related_name="replies",
        on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    message = models.TextField()

    is_staff = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply #{self.id} - Ticket {self.ticket.id}"
    
class OrderTimeline(models.Model):

    EVENT_CHOICES = [

        ("Order Placed", "Order Placed"),
        ("Payment Verified", "Payment Verified"),
        ("Payment Failed", "Payment Failed"),

        ("Order Confirmed", "Order Confirmed"),
        ("Packed", "Packed"),
        ("Shipped", "Shipped"),
        ("Out for Delivery", "Out for Delivery"),
        ("Delivered", "Delivered"),

        ("Cancelled", "Cancelled"),

        ("Return Requested", "Return Requested"),
        ("Return Approved", "Return Approved"),
        ("Return Rejected", "Return Rejected"),
        ("Return Picked Up", "Return Picked Up"),
        ("Returned", "Returned"),

        ("Refund Initiated", "Refund Initiated"),
        ("Refund Completed", "Refund Completed"),
    ]

    order = models.ForeignKey(
        Order,
        related_name="timeline",
        on_delete=models.CASCADE,
    )

    event = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
    )

    description = models.TextField(
        blank=True,
    )

    performed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.id} - {self.event}"
