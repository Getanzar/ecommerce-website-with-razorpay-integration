from django.db import models
from django.contrib.auth.models import User
from products.models import Product, ProductVariant

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart ({self.user.username})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    # 🔥 ADD THIS (IMPORTANT)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)

    quantity = models.PositiveIntegerField(default=1)

    def get_total_price(self):
        return self.product.price * self.quantity

    @property
    def size(self):
        return self.variant.size if self.variant else "N/A"

    @property
    def color(self):
        return self.variant.color.name if self.variant and self.variant.color else "N/A"