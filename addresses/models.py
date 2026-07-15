from django.db import models
from django.contrib.auth.models import User


class Address(models.Model):

    ADDRESS_TYPES = [
        ("Home", "Home"),
        ("Office", "Office"),
        ("Other", "Other"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses",
    )

    full_name = models.CharField(max_length=120)

    phone = models.CharField(max_length=15)

    address_line_1 = models.CharField(max_length=255)

    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
    )

    city = models.CharField(max_length=80)

    state = models.CharField(max_length=80)

    pincode = models.CharField(max_length=10)

    address_type = models.CharField(
        max_length=20,
        choices=ADDRESS_TYPES,
        default="Home",
    )

    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.address_type}"