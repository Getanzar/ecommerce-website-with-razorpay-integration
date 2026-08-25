from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify
from decimal import Decimal, ROUND_HALF_UP


class FoodServiceArea(models.Model):
    pincode = models.CharField(
        max_length=6,
        unique=True,
        validators=[RegexValidator(r"^\d{6}$", "Enter a valid 6-digit pincode.")],
    )
    city = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("pincode",)

    def __str__(self):
        return f"{self.pincode}{' - ' + self.city if self.city else ''}"


class Restaurant(models.Model):
    seller = models.OneToOneField(
        "accounts.SellerProfile", related_name="restaurant", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="restaurants/", blank=True, null=True)
    cuisine = models.CharField(max_length=150, blank=True)
    pincode = models.CharField(
        max_length=6, default="",
        validators=[RegexValidator(r"^\d{6}$", "Enter a valid 6-digit pincode.")],
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    gps_accuracy_meters = models.PositiveIntegerField(blank=True, null=True)
    gps_verified_at = models.DateTimeField(auto_now=True)
    preparation_minutes = models.PositiveSmallIntegerField(default=30)
    minimum_order = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    accepts_orders = models.BooleanField(default=True)
    service_areas = models.ManyToManyField(FoodServiceArea, related_name="restaurants", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "restaurant"
            slug = base
            number = 1
            while Restaurant.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                number += 1
                slug = f"{base}-{number}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MenuSection(models.Model):
    restaurant = models.ForeignKey(Restaurant, related_name="sections", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "name")
        unique_together = (("restaurant", "name"),)

    def __str__(self):
        return f"{self.restaurant}: {self.name}"


class MenuItem(models.Model):
    FOOD_TYPES = (("veg", "Vegetarian"), ("non_veg", "Non-vegetarian"), ("egg", "Contains egg"))
    restaurant = models.ForeignKey(Restaurant, related_name="menu_items", on_delete=models.CASCADE)
    section = models.ForeignKey(MenuSection, related_name="items", on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="food/menu/", blank=True, null=True)
    food_type = models.CharField(max_length=10, choices=FOOD_TYPES, default="veg")
    is_available = models.BooleanField(default=True)
    accepts_notes = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("section__display_order", "name")

    @property
    def starting_price(self):
        option = self.options.filter(is_available=True).order_by("price").first()
        return option.customer_price if option else None

    def __str__(self):
        return self.name


class MenuItemOption(models.Model):
    item = models.ForeignKey(MenuItem, related_name="options", on_delete=models.CASCADE)
    name = models.CharField(max_length=50, default="Regular")
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ("price", "id")
        unique_together = (("item", "name"),)

    def __str__(self):
        return f"{self.item} - {self.name}"

    @property
    def customer_price(self):
        fee = self.item.restaurant.seller.commission_percent
        return (self.price * (Decimal("1") + fee / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class FoodOrder(models.Model):
    STATUS_CHOICES = (
        ("placed", "Placed"), ("accepted", "Accepted"),
        ("preparing", "Preparing"), ("ready", "Ready for delivery"),
        ("out_for_delivery", "Out for delivery"), ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )
    PAYMENT_CHOICES = (("cod", "Cash on delivery"), ("online", "Online payment"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="food_orders", on_delete=models.PROTECT)
    restaurant = models.ForeignKey(Restaurant, related_name="orders", on_delete=models.PROTECT)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    gps_accuracy_meters = models.PositiveIntegerField(blank=True, null=True)
    gps_verified_at = models.DateTimeField(auto_now_add=True, null=True)
    include_cutlery = models.BooleanField(default=False)
    delivery_note = models.CharField(max_length=300, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default="cod")
    payment_status = models.CharField(max_length=20, default="Pending")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="placed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Food order #{self.pk} - {self.restaurant}"


class FoodOrderItem(models.Model):
    order = models.ForeignKey(FoodOrder, related_name="items", on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    option = models.ForeignKey(MenuItemOption, on_delete=models.PROTECT)
    item_name = models.CharField(max_length=160)
    option_name = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(default=1)
    customer_note = models.CharField(max_length=300, blank=True)

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class FoodSellerSettlement(models.Model):
    STATUS_CHOICES = (("scheduled", "Scheduled"), ("processing", "Processing"), ("paid", "Paid"), ("failed", "Failed"), ("offset", "Offset"))
    seller = models.ForeignKey("accounts.SellerProfile", related_name="food_settlements", on_delete=models.PROTECT)
    order = models.OneToOneField(FoodOrder, related_name="seller_settlement", on_delete=models.PROTECT)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deductions_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tcs_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    scheduled_for = models.DateTimeField()
    provider_payout_id = models.CharField(max_length=100, blank=True)
    failure_reason = models.TextField(blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def payout_amount(self):
        return max(
            self.net_amount - self.deductions_amount - self.delivery_charge - self.tcs_amount,
            Decimal("0.00"),
        )

    @property
    def payout_reference_key(self):
        return f"food-{self.pk}"
