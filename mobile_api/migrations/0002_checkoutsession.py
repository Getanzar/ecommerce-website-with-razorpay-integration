import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mobile_api", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="CheckoutSession", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        ("order_kind", models.CharField(choices=[("shop", "Shop"), ("food", "Food"), ("grocery", "Grocery")], max_length=12)),
        ("address_id", models.PositiveIntegerField()), ("cart_fingerprint", models.CharField(max_length=64)),
        ("quote", models.JSONField(default=dict)), ("expires_at", models.DateTimeField()),
        ("idempotency_key", models.CharField(blank=True, max_length=80)), ("status", models.CharField(default="quoted", max_length=20)),
        ("order_id", models.PositiveIntegerField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_checkout_sessions", to=settings.AUTH_USER_MODEL)),
    ], options={"constraints":[models.UniqueConstraint(condition=~models.Q(idempotency_key=""),fields=("user","order_kind","idempotency_key"),name="unique_mobile_checkout_submission")]})]
