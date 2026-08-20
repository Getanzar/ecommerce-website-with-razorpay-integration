from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


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
    business_phone = models.CharField(max_length=20, blank=True)
    business_address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)
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

    @property
    def is_approved(self):
        return self.status == "approved"

    @property
    def kyc_complete(self):
        return all(
            [
                self.legal_business_name,
                self.business_category,
                self.gstin,
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
