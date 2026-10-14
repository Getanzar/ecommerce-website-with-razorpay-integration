from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError


class UserProfile(models.Model):

    GENDER_CHOICES = [
        ("Male", "Male"),
        ("Female", "Female"),
        ("Other", "Other"),
        ("Prefer not to say", "Prefer not to say"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
    )

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
    )

    date_of_birth = models.DateField(
        blank=True,
        null=True,
    )

    profile_picture = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True,
    )
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=~models.Q(phone=""),
                name="unique_nonempty_user_phone",
            )
        ]

    def __str__(self):
        return self.user.username


class SellerProfile(models.Model):
    """Marketplace information for an account that is allowed to sell."""

    STATUS_CHOICES = [
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="seller_profile",
    )
    store_name = models.CharField(max_length=150, unique=True)
    legal_business_name = models.CharField(max_length=150, blank=True)
    business_category = models.CharField(max_length=100, blank=True)
    BUSINESS_SEGMENTS = [("shop", "Merchandise"), ("food", "Food / restaurant"), ("grocery", "Grocery / kirana")]
    business_segment = models.CharField(
        max_length=10, choices=BUSINESS_SEGMENTS, blank=True, default="",
        help_text="Select the approved selling segment. Blank legacy records require review; category descriptions never grant access.",
    )
    business_phone = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True, max_length=2000)
    logo = models.ImageField(upload_to="sellers/logos/", blank=True, null=True)
    cover_image = models.ImageField(upload_to="sellers/covers/", blank=True, null=True)
    business_address = models.TextField(blank=True)
    business_pincode = models.CharField(max_length=6, blank=True)
    business_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    business_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    business_gps_accuracy_meters = models.PositiveIntegerField(blank=True, null=True)
    business_gps_verified_at = models.DateTimeField(blank=True, null=True)
    delhivery_pickup_name = models.CharField(max_length=150, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    REGISTRATION_TYPES = [("registered", "Registered business"), ("small", "Small seller without GSTIN")]
    registration_type = models.CharField(max_length=12, choices=REGISTRATION_TYPES, default="registered")
    gst_enrolment_number = models.CharField(max_length=20, blank=True)
    pan_last4 = models.CharField(max_length=4, blank=True)
    small_seller_declaration = models.BooleanField(default=False)
    aadhaar_consent_at = models.DateTimeField(blank=True, null=True)
    IDENTITY_STATUSES = [("pending", "Awaiting identity review"), ("verified", "Verified"), ("needs_changes", "Changes required")]
    identity_status = models.CharField(max_length=20, choices=IDENTITY_STATUSES, default="pending")
    identity_review_reference = models.CharField(max_length=100, blank=True)
    identity_review_note = models.TextField(blank=True, max_length=1000)
    identity_verified_at = models.DateTimeField(blank=True, null=True)
    identity_verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_small_sellers")
    aadhaar_last4 = models.CharField(max_length=4, blank=True)
    bank_account_holder = models.CharField(max_length=150, blank=True)
    bank_account_last4 = models.CharField(max_length=4, blank=True)
    bank_ifsc_code = models.CharField(max_length=11, blank=True)
    razorpay_contact_id = models.CharField(max_length=100, blank=True)
    razorpay_fund_account_id = models.CharField(max_length=100, blank=True)
    payouts_enabled = models.BooleanField(
        default=False,
        help_text="Enable only after the seller bank account has been verified.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        help_text="Marketplace commission retained from each seller sale.",
    )
    AI_PLAN_CHOICES = [
        ("", "No AI image plan"),
        ("starter", "Starter - 25 images"),
        ("growth", "Growth - 150 images"),
        ("pro", "Pro - 400 images"),
    ]
    ai_plan = models.CharField(max_length=20, choices=AI_PLAN_CHOICES, blank=True)
    ai_image_limit = models.PositiveIntegerField(default=0)
    ai_images_used = models.PositiveIntegerField(default=0)
    ai_subscription_ends_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["store_name"]

    def clean(self):
        super().clean()
        if self.status == "approved" and self.business_segment not in dict(self.BUSINESS_SEGMENTS):
            raise ValidationError({"business_segment": "Select a selling segment before approving this seller."})
        if self.is_small_seller and (self.business_segment != "shop" or self.gstin):
            raise ValidationError("Small sellers without GSTIN can register only for merchandise, without a GSTIN.")
        if self.is_small_seller and self.status == "approved" and not self.kyc_complete:
            raise ValidationError("Complete Aadhaar identity review, enrolment eligibility and bank details before approving this small seller.")
        if self.is_small_seller and self.payouts_enabled and not (
            self.status == "approved" and self.kyc_complete and self.razorpay_contact_id and self.razorpay_fund_account_id
        ):
            raise ValidationError({"payouts_enabled": "Complete seller approval and RazorpayX bank setup before enabling payouts."})

    @property
    def is_small_seller(self):
        return self.registration_type == "small"

    @property
    def small_seller_verified(self):
        return all([
            self.business_segment == "shop", not self.gstin,
            self.gst_enrolment_number, self.pan_last4, self.small_seller_declaration,
            self.aadhaar_consent_at, self.identity_status == "verified",
            self.identity_review_reference, self.identity_verified_at, self.identity_verified_by_id,
        ])

    @property
    def is_approved(self):
        return self.status == "approved" and (not self.is_small_seller or self.kyc_complete)

    @property
    def kyc_complete(self):
        return all(
            [
                self.legal_business_name,
                self.business_category,
                self.business_segment in dict(self.BUSINESS_SEGMENTS),
                self.business_pincode,
                self.business_latitude is not None,
                self.business_longitude is not None,
                self.business_gps_verified_at,
                self.small_seller_verified if self.is_small_seller else self.gstin,
                self.aadhaar_last4,
                self.bank_account_holder,
                self.bank_account_last4,
                self.bank_ifsc_code,
            ]
        )

    def __str__(self):
        return self.store_name

    @property
    def ai_subscription_active(self):
        return bool(
            self.ai_plan
            and self.ai_subscription_ends_at
            and self.ai_subscription_ends_at > timezone.now()
        )

    @property
    def ai_images_remaining(self):
        if not self.ai_subscription_active:
            return 0
        return max(self.ai_image_limit - self.ai_images_used, 0)


class SellerAIPlanPurchase(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("paid", "Paid")]

    seller = models.ForeignKey(
        SellerProfile, related_name="ai_plan_purchases", on_delete=models.CASCADE
    )
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    amount_paise = models.PositiveIntegerField()
    plan_code = models.CharField(max_length=20)
    image_limit = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)


class EmailOTP(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="email_otp",
    )

    otp = models.CharField(
        max_length=6,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    expires_at = models.DateTimeField()

    attempts = models.PositiveIntegerField(
        default=0,
    )

    is_verified = models.BooleanField(
        default=False,
    )

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.email} OTP"


class PasswordResetOTP(models.Model):
    """Short-lived email code used only for password recovery."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_otp",
    )
    otp = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Password reset for {self.user.email}"
