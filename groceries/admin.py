from django.contrib import admin
from .models import GroceryCategory, GroceryOrder, GroceryOrderItem, GroceryProduct, GroceryServiceArea, GroceryStore

admin.site.register([GroceryServiceArea, GroceryStore, GroceryCategory, GroceryProduct, GroceryOrder, GroceryOrderItem])
