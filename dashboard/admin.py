from django.contrib import admin

from .models import AdminAuditLog, CustomerAdminNote


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "entity_type", "entity_id", "summary")
    list_filter = ("action", "entity_type", "created_at")
    search_fields = ("summary", "entity_id", "actor__username")
    readonly_fields = ("actor", "action", "entity_type", "entity_id", "summary", "metadata", "ip_address", "created_at")


admin.site.register(CustomerAdminNote)
