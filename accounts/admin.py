from django.contrib import admin
from .models import SellerAIPlanPurchase, SellerProfile, UserProfile

admin.site.register(UserProfile)


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "store_name",
        "legal_business_name",
        "user",
        "business_category",
        "business_segment",
        "registration_type",
        "identity_status",
        "status",
        "delhivery_pickup_name",
        "commission_percent",
        "payouts_enabled",
        "ai_plan",
        "ai_images_used",
        "created_at",
    )
    list_filter = ("status", "business_segment", "registration_type", "identity_status")
    readonly_fields = ("aadhaar_image_review","aadhaar_consent_at", "identity_verified_at", "identity_verified_by", "identity_status", "identity_review_reference")
    search_fields = (
        "store_name",
        "legal_business_name",
        "gstin",
        "delhivery_pickup_name",
        "user__username",
        "user__email",
    )
    list_editable = ("status", "commission_percent", "payouts_enabled")

    @admin.display(description="Aadhaar document")
    def aadhaar_image_review(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if obj and obj.aadhaar_image:
            return format_html('<a href="{}">View private Aadhaar photo in operations dashboard</a>', reverse("seller_aadhaar_image", args=[obj.pk]))
        return "No document uploaded"

    def get_exclude(self, request, obj=None):
        excluded = (*(super().get_exclude(request, obj) or ()), "aadhaar_image")
        if obj and obj.is_small_seller:
            return (*excluded, "pan_last4", "gst_enrolment_number")
        return excluded


@admin.register(SellerAIPlanPurchase)
class SellerAIPlanPurchaseAdmin(admin.ModelAdmin):
    list_display = ("seller", "plan_code", "image_limit", "amount_paise", "status", "razorpay_payment_id", "created_at")
    list_filter = ("status",)
    search_fields = ("seller__store_name", "razorpay_order_id", "razorpay_payment_id")
    readonly_fields = ("razorpay_order_id", "razorpay_payment_id", "amount_paise", "plan_code", "image_limit", "status", "paid_at")
