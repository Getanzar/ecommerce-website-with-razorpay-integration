from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="CustomerCareRequest", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("order_kind", models.CharField(choices=[("shop", "Shop"), ("food", "Food"), ("grocery", "Grocery")], max_length=12)),
        ("order_id", models.PositiveIntegerField()),
        ("request_type", models.CharField(choices=[("return", "Return"), ("support", "Support")], max_length=12)),
        ("reason", models.CharField(max_length=100)), ("message", models.TextField(blank=True)),
        ("status", models.CharField(default="Open", max_length=20)), ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mobile_care_requests", to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ("-created_at",), "constraints": [models.UniqueConstraint(fields=("user", "order_kind", "order_id", "request_type"), name="one_open_mobile_request_per_order_type")]})]
