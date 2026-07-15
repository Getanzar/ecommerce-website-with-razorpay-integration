from django.contrib import admin
from .models import Order, OrderItem, ReturnRequest , SupportTicket

from django.utils import timezone


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "product_color",
        "product_size",
        "quantity",
        "price",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "status",
        "payment_status",
        "payment_method",
        "total_price",
        "created_at",
    )

    list_filter = (
        "status",
        "payment_status",
        "payment_method",
        "created_at",
    )

    search_fields = (
        "user__username",
        "full_name",
        "phone",
        "razorpay_order_id",
        "tracking_number",
    )

    inlines = [OrderItemInline]

    fieldsets = (
        ("Customer", {
            "fields": (
                "user",
                "full_name",
                "phone",
            )
        }),

        ("Shipping Address", {
            "fields": (
                "address",
                "city",
                "state",
                "pincode",
            )
        }),

        ("Order", {
            "fields": (
                "status",
                "total_price",
            )
        }),

        ("Payment", {
            "fields": (
                "payment_method",
                "payment_status",
                "razorpay_order_id",
                "razorpay_payment_id",
                "razorpay_signature",
            )
        }),

        ("Courier", {
            "fields": (
                "courier",
                "tracking_number",
                "awb_number",
                "delivery_status",
                "eta",
            )
        }),

        ("Cancellation", {
            "fields": (
                "cancel_reason",
                "cancelled_at",
            )
        }),

        ("Delivery", {
            "fields": (
                "delivered_at",
                "returned_at",
            )
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product_name",
        "product_color",
        "product_size",
        "quantity",
        "price",
    )



@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "order",
        "user",
        "reason",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "reason",
    )

    search_fields = (
        "user__username",
        "order__id",
    )

    actions = [
        "approve_return",
        "reject_return",
    ]

    @admin.action(description="Approve selected return requests")
    def approve_return(self, request, queryset):

        for obj in queryset:

            obj.status = "Approved"
            obj.save()

            obj.order.status = "Returned"
            obj.order.returned_at = timezone.now()
            obj.order.save()

    @admin.action(description="Reject selected return requests")
    def reject_return(self, request, queryset):

        queryset.update(status="Rejected")

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "user",
        "issue",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "issue",
    )

    search_fields = (
        "user__username",
        "order__id",
    )