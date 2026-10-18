from django.contrib import admin
from .models import FoodDeliveryAreaRequest, FoodOrder, FoodOrderItem, FoodSellerSettlement, FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant


@admin.register(FoodDeliveryAreaRequest)
class FoodDeliveryAreaRequestAdmin(admin.ModelAdmin):
    list_display = ("pincode", "service", "user", "created_at", "reviewed")
    list_filter = ("service", "reviewed", "created_at", "pincode")
    search_fields = ("pincode", "comment", "user__username")
    readonly_fields = ("pincode", "service", "comment", "user", "created_at")
    list_editable = ("reviewed",)
    date_hierarchy = "created_at"

admin.site.register(FoodSellerSettlement)

admin.site.register(FoodServiceArea)
admin.site.register(Restaurant)
admin.site.register(MenuSection)
admin.site.register(MenuItem)
admin.site.register(MenuItemOption)
admin.site.register(FoodOrder)
admin.site.register(FoodOrderItem)
