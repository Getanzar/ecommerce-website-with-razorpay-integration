from django import forms
from django.contrib import admin

from .models import AccountDeletionRequest, CustomerCareReply, CustomerCareRequest
from .models import DeviceSession, PushDevice, Notification, DeliveryEvidence, SellerCase
from .models import PushReceipt
from django.db import transaction
from django.utils import timezone


class ReplyInline(admin.TabularInline):
    model = CustomerCareReply
    fields = ("user", "message", "attachment", "is_staff", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class SupportForm(forms.ModelForm):
    reply = forms.CharField(required=False, max_length=5000, widget=forms.Textarea,
                            help_text="A new reply visible to the customer in the mobile support inbox.")

    class Meta:
        model = CustomerCareRequest
        fields = ("status",)


@admin.register(CustomerCareRequest)
class CustomerCareAdmin(admin.ModelAdmin):
    form = SupportForm
    list_display = ("id", "user", "reason", "status", "order_kind", "order_id", "updated_at")
    list_filter = ("status", "request_type", "order_kind")
    search_fields = ("reason", "message", "user__username", "user__email")
    readonly_fields = ("user", "reason", "message", "attachment", "order_kind", "order_id", "order_item_id", "request_type", "created_at", "updated_at")
    fields = readonly_fields + ("status", "reply")
    inlines = (ReplyInline,)

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.cleaned_data.get("reply"):
            CustomerCareReply.objects.create(request=obj, user=request.user,
                                            message=form.cleaned_data["reply"], is_staff=True)


@admin.register(AccountDeletionRequest)
class AccountDeletionAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("user", "reason", "created_at", "status")
    actions = ["disable_account", "erase_customer_account"]

    @admin.action(description="Execute customer account deletion after open obligations are resolved")
    def erase_customer_account(self, request, queryset):
        from .deletion import execute_deletion
        from rest_framework.exceptions import ValidationError
        from dashboard.security import audit
        if not request.user.is_superuser:
            self.message_user(request, "Only a superuser can execute account deletion.", level="error")
            return
        for pk in queryset.values_list("pk", flat=True):
            try:
                row = execute_deletion(pk)
                audit(request, "account.deletion.execute", row, "Customer account data erased; operational records retained")
                self.message_user(request, f"Deletion request #{pk} completed.")
            except ValidationError as exc:
                self.message_user(request, f"Request #{pk}: {exc.detail}", level="error")

    @admin.action(description="Disable account access and revoke all sessions (retain order records)")
    def disable_account(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only a superuser can execute account deletion requests.", level="error")
            return
        from rest_framework.authtoken.models import Token
        from dashboard.security import audit
        for pk in queryset.values_list("pk", flat=True):
            with transaction.atomic():
                row = AccountDeletionRequest.objects.select_for_update().select_related("user").get(pk=pk)
                if row.status != "Pending":
                    continue
                user = row.user
                if user.is_staff or user.is_superuser:
                    self.message_user(request, "Staff accounts require a separate administrator access review.", level="error")
                    continue
                user.is_active = False
                user.set_unusable_password()
                user.save(update_fields=["is_active", "password"])
                DeviceSession.objects.filter(user=user).update(revoked_at=timezone.now())
                Token.objects.filter(user=user).delete()
                PushDevice.objects.filter(user=user).update(active=False)
                row.status = "Access disabled"
                row.save(update_fields=["status"])
                audit(request, "account.deletion.disable", row, "Account access disabled; retained data requires retention review")

    def has_add_permission(self, request):
        return False


@admin.register(SellerCase)
class SellerCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "seller", "kind", "order_kind", "order_id", "status", "updated_at")
    list_filter = ("kind", "status", "order_kind")
    readonly_fields = ("seller", "kind", "order_kind", "order_id", "order_item_id", "reason", "created_at", "updated_at", "executed_at", "refund")
    search_fields = ("reason", "resolution")
    actions = ["execute_case"]

    @admin.action(description="Execute eligible cancellation/refund requests (or retry reserved refund)")
    def execute_case(self, request, queryset):
        from .case_services import prepare_case, submit_case_refund
        from rest_framework.exceptions import ValidationError
        from dashboard.security import audit
        if not request.user.is_superuser:
            self.message_user(request, "Only a superuser can execute refunds and cancellations.", level="error")
            return
        for pk in queryset.values_list("pk", flat=True):
            try:
                case = prepare_case(pk)
                audit(request, "seller.case.execute", case, "Seller case execution requested", refund_id=case.refund_id)
                submit_case_refund(case)
                self.message_user(request, f"Case #{pk} executed or awaiting refund confirmation.")
            except ValidationError as exc:
                self.message_user(request, f"Case #{pk}: {exc.detail}", level="error")

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from dashboard.security import audit
        audit(request, "seller.case.review", obj, f"Seller case {obj.status}")
        Notification.objects.create(user=obj.seller.user, title="Seller request updated", body=f"Request #{obj.pk}: {obj.status}", data={"target": "seller", "order_id": obj.order_id, "kind": obj.order_kind})


@admin.register(DeliveryEvidence)
class DeliveryEvidenceAdmin(admin.ModelAdmin):
    list_display = ("delivery", "kind", "reason", "actor", "created_at")
    list_filter = ("kind",)
    readonly_fields = ("delivery", "kind", "reason", "proof_link", "actor", "created_at")
    fields = readonly_fields

    @admin.display(description="Delivery photo")
    def proof_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        return format_html('<a href="{}">View private delivery photo</a>', reverse("ops_delivery_proof", args=[obj.pk])) if obj.photo else "No photo"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "push_status", "attempts", "created_at")
    list_filter = ("push_status", "category")
    readonly_fields = ("user", "title", "body", "data", "category", "read_at", "created_at", "push_status", "attempts")

    def has_add_permission(self, request):
        return False


@admin.register(PushReceipt)
class PushReceiptAdmin(admin.ModelAdmin):
    list_display = ("ticket_id", "device", "status", "error", "created_at")
    list_filter = ("status", "error")
    readonly_fields = ("ticket_id", "device", "status", "error", "created_at")

    def has_add_permission(self, request):
        return False
