from django.contrib import admin
from .models import (
    Category,
    SubCategory,
    Product,
    ProductImage,
    ProductColor,
    ProductVariant,
    ProductReview,
    Wishlist,
)


# -----------------------------------
# Product Images
# -----------------------------------
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


# -----------------------------------
# Product Colors
# -----------------------------------
class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 1


# -----------------------------------
# Product Variants
# -----------------------------------
class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


# -----------------------------------
# SubCategories
# -----------------------------------
class SubCategoryInline(admin.TabularInline):
    model = SubCategory
    extra = 1


# -----------------------------------
# Categories
# -----------------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "image",
        "background_image",
    )

    search_fields = ("name",)

    prepopulated_fields = {
        "slug": ("name",)
    }

    fields = (
        "name",
        "slug",
        "image",
        "background_image",
    )

    inlines = [SubCategoryInline]


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


# -----------------------------------
# Products
# -----------------------------------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "subcategory",
        "price",
        "stock",
        "average_rating",
        "review_count",
        "created",
    )

    list_filter = (
        "category",
        "subcategory",
        "product_type",
        "created",
    )

    search_fields = (
        "name",
        "description",
        "category__name",
        "subcategory__name",
    )

    readonly_fields = (
        "average_rating",
        "review_count",
    )

    prepopulated_fields = {
        "slug": ("name",)
    }

    inlines = (
        ProductImageInline,
        ProductColorInline,
        ProductVariantInline,
    )


# -----------------------------------
# Product Images
# -----------------------------------
@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "image",
    )


# -----------------------------------
# Product Colors
# -----------------------------------
@admin.register(ProductColor)
class ProductColorAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "name",
        "hex_code",
        "image",
        "display_order",
    )

    fields = (
        "product",
        "name",
        "hex_code",
        "image",
        "display_order",
    )

    list_filter = (
        "product",
    )

    search_fields = (
        "product__name",
        "name",
    )


# -----------------------------------
# Product Variants
# -----------------------------------
@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "color",
        "size",
        "final_price",
        "stock",
        "is_active",
    )

    list_filter = (
        "product",
        "color",
        "size",
        "is_active",
    )

    search_fields = (
        "product__name",
        "sku",
    )


# -----------------------------------
# Product Reviews
# -----------------------------------
@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "user",
        "rating",
        "is_verified_purchase",
        "is_approved",
        "created_at",
    )

    list_filter = (
        "rating",
        "is_verified_purchase",
        "is_approved",
    )

    search_fields = (
        "product__name",
        "user__username",
        "review",
    )

    list_editable = (
        "is_approved",
    )


# -----------------------------------
# Wishlist
# -----------------------------------
@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "product",
        "created_at",
    )

    search_fields = (
        "user__username",
        "product__name",
    )

    list_filter = (
        "created_at",
    )