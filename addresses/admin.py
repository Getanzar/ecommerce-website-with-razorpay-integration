from django.contrib import admin
from .models import Address


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "user",
        "full_name",
        "city",
        "address_type",
        "is_default",
    )

    list_filter = (
        "address_type",
        "is_default",
    )

    search_fields = (
        "user__username",
        "full_name",
        "phone",
    )