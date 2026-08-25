from django.contrib import admin
from .models import GroceryCategory, GroceryOrder, GroceryOrderItem, GroceryProduct, GrocerySellerSettlement, GroceryServiceArea, GroceryStore

admin.site.register([GroceryServiceArea, GroceryStore, GroceryCategory, GroceryProduct, GroceryOrder, GroceryOrderItem, GrocerySellerSettlement])
