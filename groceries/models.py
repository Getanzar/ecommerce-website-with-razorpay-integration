from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify


class GroceryServiceArea(models.Model):
    DELIVERY_CHOICES = (("local", "Store/local rider"), ("delhivery", "Delhivery parcel"))
    pincode = models.CharField(max_length=6, unique=True, validators=[RegexValidator(r"^\d{6}$")])
    city = models.CharField(max_length=80, blank=True)
    delivery_mode = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default="local")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.pincode} - {self.city}" if self.city else self.pincode


class GroceryStore(models.Model):
    seller = models.OneToOneField("accounts.SellerProfile", related_name="grocery_store", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="groceries/stores/", blank=True, null=True)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    minimum_order = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    estimated_delivery_minutes = models.PositiveSmallIntegerField(default=60)
    accepts_orders = models.BooleanField(default=True)
    service_areas = models.ManyToManyField(GroceryServiceArea, related_name="stores", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "kirana-store"
            candidate, number = base, 1
            while GroceryStore.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                number += 1
                candidate = f"{base}-{number}"
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class GroceryCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    image = models.ImageField(upload_to="groceries/categories/", blank=True, null=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name


class GroceryProduct(models.Model):
    store = models.ForeignKey(GroceryStore, related_name="products", on_delete=models.CASCADE)
    category = models.ForeignKey(GroceryCategory, related_name="products", on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    brand = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to="groceries/products/", blank=True, null=True)
    unit = models.CharField(max_length=40, help_text="For example: 1 kg, 500 ml, pack of 6")
    mrp = models.DecimalField(max_digits=9, decimal_places=2)
    price = models.DecimalField(max_digits=9, decimal_places=2, help_text="Store selling price before platform fee")
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_perishable = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("category__display_order", "name")

    @property
    def customer_price(self):
        fee = self.store.seller.commission_percent
        return (self.price * (Decimal("1") + fee / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def in_stock(self):
        return self.is_active and self.stock > 0

    def __str__(self):
        return f"{self.store}: {self.name}"


class GroceryOrder(models.Model):
    STATUS_CHOICES = (("placed", "Placed"), ("accepted", "Accepted"), ("packing", "Packing"), ("ready", "Ready"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="grocery_orders", on_delete=models.PROTECT)
    store = models.ForeignKey(GroceryStore, related_name="orders", on_delete=models.PROTECT)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6)
    substitution_preference = models.CharField(max_length=20, choices=(("refund", "Refund unavailable items"), ("contact", "Contact me for substitutes")), default="refund")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=(("cod", "Cash on delivery"),), default="cod")
    payment_status = models.CharField(max_length=20, default="Pending")
    delivery_mode = models.CharField(max_length=20, choices=GroceryServiceArea.DELIVERY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="placed")
    courier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)


class GroceryOrderItem(models.Model):
    order = models.ForeignKey(GroceryOrder, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(GroceryProduct, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=180)
    unit = models.CharField(max_length=40)
    unit_price = models.DecimalField(max_digits=9, decimal_places=2)
    quantity = models.PositiveIntegerField()

    @property
    def total(self):
        return self.unit_price * self.quantity
