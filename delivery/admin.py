from django.contrib import admin
from django.utils import timezone

from .models import DeliveryAgentProfile, DeliveryCollection, DeliveryEarning, DeliveryZone, LocalDelivery


@admin.action(description="Approve selected delivery agents")
def approve_agents(modeladmin, request, queryset):
    queryset.update(status="approved", verified_at=timezone.now())


@admin.register(DeliveryAgentProfile)
class DeliveryAgentProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "pincode", "status", "is_online", "created_at")
    list_filter = ("status", "is_online", "pincode")
    search_fields = ("full_name", "phone", "user__username", "pincode")
    actions = (approve_agents,)


@admin.register(LocalDelivery)
class LocalDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "order_kind", "pincode", "agent", "status", "created_at")
    list_filter = ("status", "pincode")
    search_fields = ("customer_name", "customer_phone", "pickup_name")


admin.site.register(DeliveryZone)
admin.site.register(DeliveryEarning)


@admin.register(DeliveryCollection)
class DeliveryCollectionAdmin(admin.ModelAdmin):
    list_display = ("delivery", "amount", "method", "status", "qr_id", "paid_at")
    list_filter = ("method", "status")
    search_fields = ("qr_id", "delivery__customer_name")
    readonly_fields = ("delivery", "amount", "method", "status", "qr_id", "qr_image_url", "payment", "paid_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
