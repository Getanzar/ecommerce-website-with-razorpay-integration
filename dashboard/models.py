from django.conf import settings
from django.db import models


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="admin_audit_events",
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=80, blank=True, db_index=True)
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = (("access_operations_dashboard", "Can access operations dashboard"),)

    def __str__(self):
        return f"{self.actor or 'System'}: {self.summary}"


class CustomerAdminNote(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="admin_notes", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="authored_customer_notes", on_delete=models.PROTECT
    )
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
