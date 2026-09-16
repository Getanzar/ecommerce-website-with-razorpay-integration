from django.contrib.auth.models import User

from accounts.models import SellerProfile
from food.models import FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant
from groceries.models import GroceryCategory, GroceryProduct, GroceryServiceArea, GroceryStore
from products.models import Category, Product, ProductColor, ProductVariant


customer, _ = User.objects.get_or_create(username="ui-customer")
customer.set_password("UI-review-123")
customer.save()

# Merchandise fixtures for the Expo customer app. These records live only in
# .ui_review.sqlite3 and make cart/variant/checkout testing production-safe.
catalog = [
    ("Kids", "kids", "First Day Boys Full-Sleeve Hooded T-Shirt & Pant Set", "first-day-boys-set", "1999.00", "products/kid_3.jpg", ["4-5 Y", "6-7 Y"]),
    ("Men", "men", "Premium Cotton Full-Sleeve Shirt", "premium-cotton-shirt", "899.00", "products/men-cotton-lining-full-sleeve-shirt-1000x1000.webp", ["M", "L", "XL"]),
    ("Women", "women", "Elegant Green Occasion Suit", "elegant-green-suit", "1499.00", "products/suitgreen.jpg", ["S", "M", "L"]),
    ("Men", "men", "Classic Black Grey Jeans", "classic-black-grey-jeans", "1099.00", "products/black-grey_jeans.jpg", ["30", "32", "34"]),
]
for category_name, category_slug, name, slug, price, image, sizes in catalog:
    product_category, _ = Category.objects.get_or_create(name=category_name, defaults={"slug": category_slug})
    product, _ = Product.objects.get_or_create(
        slug=slug,
        defaults={
            "category": product_category,
            "name": name,
            "description": "Comfortable, quality-tested fashion selected for the ZIYAMART local app preview.",
            "price": price,
            "image": image,
            "stock": 30,
            "is_active": True,
            "moderation_status": Product.MODERATION_APPROVED,
        },
    )
    color, _ = ProductColor.objects.get_or_create(product=product, name="Default", defaults={"hex_code": "#17243A"})
    for size in sizes:
        ProductVariant.objects.get_or_create(product=product, color=color, size=size, defaults={"stock": 10, "is_active": True})

grocery_owner, _ = User.objects.get_or_create(username="ui-grocery-owner")
grocery_seller, _ = SellerProfile.objects.get_or_create(
    user=grocery_owner,
    defaults={
        "store_name": "Green Basket Kirana",
        "business_category": "Grocery",
        "status": "approved",
        "commission_percent": 10,
    },
)
grocery_area, _ = GroceryServiceArea.objects.get_or_create(
    pincode="243638", defaults={"city": "Sahaswan", "delivery_mode": "local"},
)
store, _ = GroceryStore.objects.get_or_create(
    seller=grocery_seller,
    defaults={
        "name": "Green Basket Kirana",
        "description": "Fresh staples, household essentials and everyday favourites from your neighbourhood store.",
        "address": "Main Market, Sahaswan",
        "pincode": "243638",
        "latitude": "28.073100",
        "longitude": "78.750200",
        "gps_accuracy_meters": 12,
        "phone": "9999999999",
        "delivery_fee": "25.00",
        "minimum_order": "100.00",
    },
)
store.service_areas.add(grocery_area)
category, _ = GroceryCategory.objects.get_or_create(name="Daily staples", defaults={"slug": "daily-staples"})
for name, unit, mrp, price in (
    ("Premium Whole Wheat Atta", "5 kg", "340.00", "299.00"),
    ("Classic Basmati Rice", "1 kg", "180.00", "155.00"),
    ("Full Cream Milk", "1 litre", "72.00", "68.00"),
):
    GroceryProduct.objects.get_or_create(
        store=store, name=name,
        defaults={"category": category, "unit": unit, "mrp": mrp, "price": price, "stock": 20},
    )

food_owner, _ = User.objects.get_or_create(username="ui-food-owner")
food_seller, _ = SellerProfile.objects.get_or_create(
    user=food_owner,
    defaults={
        "store_name": "Spice Route Kitchen",
        "business_category": "Restaurant",
        "status": "approved",
        "commission_percent": 10,
    },
)
food_area, _ = FoodServiceArea.objects.get_or_create(pincode="243638", defaults={"city": "Sahaswan"})
restaurant, _ = Restaurant.objects.get_or_create(
    seller=food_seller,
    defaults={
        "name": "Spice Route Kitchen",
        "description": "Comforting local meals cooked fresh for every order.",
        "pincode": "243638",
        "latitude": "28.073200",
        "longitude": "78.750300",
        "gps_accuracy_meters": 12,
        "delivery_fee": "25.00",
    },
)
restaurant.service_areas.add(food_area)
section, _ = MenuSection.objects.get_or_create(restaurant=restaurant, name="Popular picks")
item, _ = MenuItem.objects.get_or_create(restaurant=restaurant, section=section, name="Paneer Biryani")
MenuItemOption.objects.get_or_create(item=item, name="Full", defaults={"price": "220.00"})
