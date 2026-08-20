from django.contrib import admin
from .models import FoodOrder, FoodOrderItem, FoodSellerSettlement, FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant

admin.site.register(FoodSellerSettlement)

admin.site.register(FoodServiceArea)
admin.site.register(Restaurant)
admin.site.register(MenuSection)
admin.site.register(MenuItem)
admin.site.register(MenuItemOption)
admin.site.register(FoodOrder)
admin.site.register(FoodOrderItem)
