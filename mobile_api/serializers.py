from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from addresses.models import Address
from cart.models import CartItem
from products.models import Category, Product, ProductColor, ProductImage, ProductReview, ProductVariant, Wishlist
from food.models import MenuItem, MenuItemOption, Restaurant
from groceries.models import GroceryCategory, GroceryProduct, GroceryStore
from orders.models import Order, OrderItem


def absolute_url(request, image):
    if not image:
        return None
    url = image.url
    return request.build_absolute_uri(url) if request else url


class UserSerializer(serializers.ModelSerializer):
    can_access_operations = serializers.SerializerMethodField()

    def get_can_access_operations(self, obj):
        from dashboard.security import can_access_operations
        return can_access_operations(obj)

    phone = serializers.CharField(source="profile.phone", allow_blank=True, required=False)
    gender = serializers.ChoiceField(source="profile.gender", choices=["", "Male", "Female", "Other", "Prefer not to say"], required=False)
    date_of_birth = serializers.DateField(source="profile.date_of_birth", allow_null=True, required=False)
    profile_picture = serializers.ImageField(source="profile.profile_picture", required=False, write_only=True)
    profile_picture_url = serializers.SerializerMethodField()
    email_verified = serializers.BooleanField(source="profile.email_verified", read_only=True)

    def get_profile_picture_url(self, obj):
        return absolute_url(self.context.get("request"), obj.profile.profile_picture)

    def validate_date_of_birth(self, value):
        from django.utils import timezone
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate(self, attrs):
        from accounts.forms import CustomerProfileForm
        profile = attrs.get("profile", {})
        data = {key: attrs.get(key, getattr(self.instance, key)) for key in ("username", "first_name", "last_name", "email")}
        data.update({key: profile.get(key, getattr(self.instance.profile, key)) for key in ("phone", "gender", "date_of_birth")})
        form = CustomerProfileForm(data, {"profile_picture": profile["profile_picture"]} if profile.get("profile_picture") else None, user=self.instance)
        if not form.is_valid():
            raise serializers.ValidationError(dict(form.errors))
        if "phone" in profile:
            profile["phone"] = form.cleaned_data["phone"]
        return attrs

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email", "phone", "email_verified", "gender", "date_of_birth", "profile_picture", "profile_picture_url", "can_access_operations")
        read_only_fields = ("id", "email", "email_verified")

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        instance = super().update(instance, validated_data)
        profile = instance.profile
        if "phone" in profile_data and profile.phone != profile_data["phone"]:
            profile.phone_verified = False
        for key, value in profile_data.items():
            setattr(profile, key, value)
        profile.save()
        return instance


class CategorySerializer(serializers.ModelSerializer):
    icon = serializers.CharField(read_only=True)
    electronics_types = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    background_image_url = serializers.SerializerMethodField()
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "icon", "image_url", "background_image_url", "subcategories", "electronics_types")

    def get_electronics_types(self, obj):
        from products.electronics import ELECTRONICS
        return [{"key": key, "name": item["name"], "icon": item["icon"]} for key, item in ELECTRONICS.items()] if obj.slug == "electronics" else []

    def get_image_url(self, obj):
        return absolute_url(self.context.get("request"), obj.image)

    def get_background_image_url(self, obj):
        return absolute_url(self.context.get("request"), obj.background_image)

    def get_subcategories(self, obj):
        return [{"id": row.id, "name": row.name, "icon": row.icon} for row in obj.subcategories.all()]


class ColorSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductColor
        fields = ("id", "name", "hex_code", "image_url")

    def get_image_url(self, obj):
        return absolute_url(self.context.get("request"), obj.image)


class VariantSerializer(serializers.ModelSerializer):
    color = ColorSerializer(read_only=True)
    price = serializers.DecimalField(source="customer_price_with_tax", max_digits=10, decimal_places=2, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ("id", "color", "size", "stock", "price", "image_url")

    def get_image_url(self, obj):
        return absolute_url(self.context.get("request"), obj.image)


class ProductSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(source="storefront_price", max_digits=10, decimal_places=2, read_only=True)
    image_url = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    rating = serializers.FloatField(source="average_rating", read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    is_wishlisted = serializers.SerializerMethodField()
    seller_name = serializers.CharField(source="seller.store_name", read_only=True, default="ZIYAMART")

    class Meta:
        model = Product
        fields = ("id", "name", "slug", "description", "price", "image_url", "category", "gender", "kids_age_group", "rating", "review_count", "is_wishlisted", "seller_name")

    def get_image_url(self, obj):
        return absolute_url(self.context.get("request"), obj.image)

    def get_is_wishlisted(self, obj):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and Wishlist.objects.filter(user=request.user, product=obj).exists())


class ProductDetailSerializer(ProductSerializer):
    variants = serializers.SerializerMethodField()
    gallery = serializers.SerializerMethodField()
    specifications = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + ("variants", "gallery", "specifications", "reviews")

    def get_variants(self, obj):
        rows = obj.variants.filter(is_active=True).select_related("color")
        return VariantSerializer(rows, many=True, context=self.context).data

    def get_gallery(self, obj):
        return [absolute_url(self.context.get("request"), row.image) for row in obj.images.all()]

    def get_specifications(self, obj):
        return {**obj.specifications, "category": obj.category.name, "subcategory": obj.subcategory.name if obj.subcategory else "", "product_type": obj.get_product_type_display(), "weight": f"{obj.package_weight_grams} g", "gst_rate": f"{obj.effective_gst_rate}%"}

    def get_reviews(self, obj):
        return [{"id": row.id, "username": row.user.first_name or row.user.username, "rating": row.rating, "title": row.title, "review": row.review, "verified": row.is_verified_purchase, "created_at": row.created_at} for row in obj.reviews.filter(is_approved=True).select_related("user")[:20]]


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    variant = VariantSerializer(read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ("id", "product", "variant", "quantity", "total")

    def get_total(self, obj):
        unit = obj.variant.customer_price_with_tax if obj.variant_id else obj.product.storefront_price
        return str(unit * obj.quantity)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ("id", "full_name", "phone", "address_line_1", "address_line_2", "city", "state", "pincode", "address_type", "is_default")
        read_only_fields = ("id", "is_default")

    def validate_phone(self, value):
        digits = value.replace("+91", "").replace(" ", "")
        if not digits.isdigit() or len(digits) != 10:
            raise serializers.ValidationError("Enter a valid 10-digit mobile number.")
        return digits

    def validate_pincode(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("Enter a valid 6-digit pincode.")
        return value


class MenuOptionSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(source="customer_price", max_digits=8, decimal_places=2, read_only=True)
    class Meta:
        model = MenuItemOption
        fields = ("id", "name", "price")


class MenuItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    options = MenuOptionSerializer(many=True, read_only=True)
    starting_price = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    section = serializers.CharField(source="section.name", read_only=True)
    class Meta:
        model = MenuItem
        fields = ("id", "name", "description", "food_type", "image_url", "section", "starting_price", "options")
    def get_image_url(self, obj): return absolute_url(self.context.get("request"), obj.image)


class RestaurantSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = Restaurant
        fields = ("id", "name", "slug", "description", "cuisine", "image_url", "pincode", "preparation_minutes", "minimum_order", "delivery_fee", "accepts_orders")
    def get_image_url(self, obj): return absolute_url(self.context.get("request"), obj.image)


class RestaurantDetailSerializer(RestaurantSerializer):
    menu_items = MenuItemSerializer(many=True, read_only=True)
    class Meta(RestaurantSerializer.Meta):
        fields = RestaurantSerializer.Meta.fields + ("menu_items",)


class GroceryCategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = GroceryCategory
        fields = ("id", "name", "slug", "image_url")
    def get_image_url(self, obj): return absolute_url(self.context.get("request"), obj.image)


class GroceryProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    price_with_tax = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    mrp = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    selected_option_id = serializers.SerializerMethodField()
    category = GroceryCategorySerializer(read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    class Meta:
        model = GroceryProduct
        fields = ("id", "name", "description", "brand", "image_url", "unit", "mrp", "price", "price_with_tax", "stock", "options", "selected_option_id", "is_perishable", "category", "store_name")
    def get_image_url(self, obj): return absolute_url(self.context.get("request"), obj.image)

    def selected(self, obj):
        from groceries.options import resolve_option, GroceryInventoryError
        if not hasattr(obj, "_api_selected_pack"):
            try:
                obj._api_selected_pack = resolve_option(obj)
            except GroceryInventoryError:
                obj._api_selected_pack = obj.default_option
            obj._api_selected_pack.product = obj
        return obj._api_selected_pack

    def get_price(self, obj): return f"{self.selected(obj).customer_price:.2f}"
    def get_price_with_tax(self, obj): return f"{self.selected(obj).customer_price_with_tax:.2f}"
    def get_unit(self, obj): return self.selected(obj).unit
    def get_mrp(self, obj): return f"{self.selected(obj).mrp:.2f}"
    def get_stock(self, obj): return self.selected(obj).stock
    def get_selected_option_id(self, obj): return self.selected(obj).pk
    def get_options(self, obj):
        options = getattr(obj, "pack_options", None)
        if options is None:
            options = list(obj.options.filter(is_active=True))
        rows = []
        for option in options:
            option.product = obj
            rows.append({"id": option.pk, "unit": option.unit, "mrp": f"{option.mrp:.2f}", "price": f"{option.customer_price:.2f}", "price_with_tax": f"{option.customer_price_with_tax:.2f}", "stock": option.stock, "is_default": option.is_default})
        return rows


class GroceryStoreSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = GroceryStore
        fields = ("id", "name", "slug", "description", "image_url", "address", "pincode", "phone", "minimum_order", "delivery_fee", "estimated_delivery_minutes", "accepts_orders")
    def get_image_url(self, obj): return absolute_url(self.context.get("request"), obj.image)


class GroceryStoreDetailSerializer(GroceryStoreSerializer):
    products = serializers.SerializerMethodField()
    class Meta(GroceryStoreSerializer.Meta):
        fields = GroceryStoreSerializer.Meta.fields + ("products",)
    def get_products(self, obj):
        request = self.context.get("request")
        if request and request.query_params.get("include_products") == "false":
            return []  # Updated apps load the paginated product endpoint.
        from groceries.options import available_products, with_pack_options
        rows = with_pack_options(available_products(obj.products.all()).select_related("category", "store__seller"))
        return GroceryProductSerializer(rows, many=True, context=self.context).data


class OrderItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(source="total", max_digits=10, decimal_places=2, read_only=True)
    class Meta:
        model = OrderItem
        fields = ("id", "product_name", "product_color", "product_size", "quantity", "price", "line_total", "image_url", "fulfillment_status")
    def get_image_url(self, obj): return absolute_url(self.context.get("request"), obj.product_image)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    can_return = serializers.BooleanField(source="can_request_return", read_only=True)
    class Meta:
        model = Order
        fields = ("id", "created_at", "updated_at", "total_price", "status", "payment_method", "payment_status", "full_name", "phone", "address", "city", "state", "pincode", "courier", "tracking_number", "delivery_status", "eta", "can_cancel", "can_return", "items")
    def get_can_cancel(self, obj):
        return obj.status in ("Pending", "Processing")
