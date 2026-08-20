# Generated manually for the marketplace seller foundation.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0004_emailotp"),
    ]

    operations = [
        migrations.CreateModel(
            name="SellerProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("store_name", models.CharField(max_length=150, unique=True)),
                ("business_phone", models.CharField(blank=True, max_length=20)),
                ("business_address", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending approval"),
                            ("approved", "Approved"),
                            ("suspended", "Suspended"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "commission_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=10,
                        help_text="Marketplace commission retained from each seller sale.",
                        max_digits=5,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seller_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["store_name"]},
        ),
    ]
