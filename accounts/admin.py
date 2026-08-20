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
        "status",
        "commission_percent",
        "payouts_enabled",
        "ai_plan",
        "ai_images_used",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("store_name", "legal_business_name", "gstin", "user__username", "user__email")
    list_editable = ("status", "commission_percent", "payouts_enabled")


@admin.register(SellerAIPlanPurchase)
class SellerAIPlanPurchaseAdmin(admin.ModelAdmin):
    list_display = ("seller", "plan_code", "image_limit", "amount_paise", "status", "razorpay_payment_id", "created_at")
    list_filter = ("status",)
    search_fields = ("seller__store_name", "razorpay_order_id", "razorpay_payment_id")
    readonly_fields = ("razorpay_order_id", "razorpay_payment_id", "amount_paise", "plan_code", "image_limit", "status", "paid_at")
