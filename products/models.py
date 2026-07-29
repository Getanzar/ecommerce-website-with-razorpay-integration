from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import User
from django.db.models import Avg, Count


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    # Small image/icon for the category
    image = models.ImageField(
        upload_to="categories/",
        blank=True,
        null=True
    )

    # Large background image for homepage/category cards
    background_image = models.ImageField(
        upload_to="categories/backgrounds/",
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="subcategories"
    )

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class Product(models.Model):
    PRODUCT_TYPES = [
        ("shirt", "Shirt"),
        ("jeans", "Jeans"),
        ("shoes", "Shoes"),
        ("dress", "Dress"),
        ("kidswear", "Kidswear"),
        ("accessory", "Accessory"),
    ]

    category = models.ForeignKey(
        Category,
        related_name="products",
        on_delete=models.CASCADE,
        default=6
    )

    subcategory = models.ForeignKey(
        SubCategory,
        related_name="products",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Optional: assign product to a subcategory"
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    # Base product price (used when variant price is not specified)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True
    )

    # Legacy stock (will be replaced by variant stock later)
    stock = models.PositiveIntegerField(default=0)

    # ⭐ NEW FIELD
    is_active = models.BooleanField(default=True)

    created = models.DateTimeField(auto_now_add=True)

    product_type = models.CharField(
        max_length=50,
        choices=PRODUCT_TYPES,
        default="shirt"
    )

    # Legacy sizes (will be replaced by ProductVariant later)
    available_sizes = models.JSONField(
        default=list,
        blank=True,
        help_text="Temporary field. Sizes are moving to ProductVariant."
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    @property
    def average_rating(self):
        approved_reviews = self.reviews.filter(is_approved=True)

        if not approved_reviews.exists():
            return 0

        total = sum(review.rating for review in approved_reviews)
        return round(total / approved_reviews.count(), 1)

    @property
    def review_count(self):
        return self.reviews.filter(is_approved=True).count()

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="images",
        on_delete=models.CASCADE
    )

    # Link image to a specific color
    color = models.ForeignKey(
        "ProductColor",
        related_name="gallery",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Leave empty if this image is common for all colors."
    )

    image = models.ImageField(
        upload_to="products/extra_images/"
    )

    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Images with lower numbers appear first."
    )

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        if self.color:
            return f"{self.product.name} - {self.color.name}"
        return f"{self.product.name} - General"

class ProductColor(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="colors",
        on_delete=models.CASCADE
    )

    name = models.CharField(max_length=50)

    hex_code = models.CharField(
        max_length=7,
        default="#000000",
        help_text="Example: #000000"
    )

    image = models.ImageField(
        upload_to="products/colors/",
        blank=True,
        null=True,
        help_text="Main image shown when this color is selected."
    )

    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        unique_together = ("product", "name")

    def __str__(self):
        return f"{self.product.name} - {self.name}"
    

class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="variants",
        on_delete=models.CASCADE
    )

    color = models.ForeignKey(
        ProductColor,
        related_name="variants",
        on_delete=models.CASCADE
    )

    size = models.CharField(
        max_length=30,
        help_text="Example: S, M, L, XL, XXL, 30, 32, Free Size"
    )

    stock = models.PositiveIntegerField(default=0)

    # Show or hide this variant on the website
    is_active = models.BooleanField(default=True)

    # Optional SKU
    sku = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )

    # Optional price override
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Leave blank to use the product's base price."
    )

    # Optional image specific to this color/size
    image = models.ImageField(
        upload_to="products/variants/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        unique_together = ("product", "color", "size")
        verbose_name = "Product Variant"
        verbose_name_plural = "Product Variants"

    @property
    def final_price(self):
        """
        Returns the variant price if available,
        otherwise returns the product's base price.
        """
        return self.price if self.price is not None else self.product.price

    def __str__(self):
        return f"{self.product.name} | {self.color.name} | {self.size}"


class ProductReview(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="reviews",
        on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        User,
        related_name="product_reviews",
        on_delete=models.CASCADE
    )

    rating = models.PositiveSmallIntegerField(
        default=5,
        help_text="Rating from 1 to 5"
    )

    title = models.CharField(
        max_length=100,
        blank=True
    )

    review = models.TextField()

    is_verified_purchase = models.BooleanField(default=False)

    is_approved = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

        # ⚠️ modern replacement for unique_together (recommended)
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"],
                name="unique_product_user_review"
            )
        ]

        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["user"]),
            models.Index(fields=["product", "user"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.user.username} ({self.rating}★)"
    

class Wishlist(models.Model):
    user = models.ForeignKey(
        User,
        related_name="wishlist_items",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        related_name="wishlisted_by",
        on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"
    

@property
def average_rating(self):
    return self.reviews.filter(is_approved=True).aggregate(
        avg=Avg("rating")
    )["avg"] or 0

@property
def review_count(self):
    return self.reviews.filter(is_approved=True).count()