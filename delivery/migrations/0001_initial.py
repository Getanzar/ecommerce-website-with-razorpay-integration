import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("food", "0002_food_payouts_and_payments"),
        ("groceries", "0002_seed_categories"),
    ]
    operations = [
        migrations.CreateModel(name="DeliveryZone", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("pincode", models.CharField(max_length=6, unique=True, validators=[django.core.validators.RegexValidator("^\\d{6}$", "Enter a valid 6-digit pincode.")])),
            ("city", models.CharField(max_length=80)), ("state", models.CharField(blank=True, max_length=80)),
            ("is_active", models.BooleanField(default=True)),
        ], options={"ordering": ("pincode",)}),
        migrations.CreateModel(name="DeliveryAgentProfile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("full_name", models.CharField(max_length=120)), ("phone", models.CharField(max_length=15)),
            ("address", models.TextField()), ("city", models.CharField(max_length=80)), ("state", models.CharField(max_length=80)),
            ("pincode", models.CharField(db_index=True, max_length=6, validators=[django.core.validators.RegexValidator("^\\d{6}$", "Enter a valid 6-digit pincode.")])),
            ("vehicle_type", models.CharField(choices=[("bicycle", "Bicycle"), ("motorcycle", "Motorcycle/Scooter"), ("ev", "Electric vehicle"), ("other", "Other")], max_length=20)),
            ("vehicle_number", models.CharField(blank=True, max_length=30)), ("aadhaar_last4", models.CharField(max_length=4)),
            ("driving_license_number", models.CharField(blank=True, max_length=40)),
            ("id_document", models.ImageField(blank=True, null=True, upload_to="delivery/identity/")),
            ("driving_license_image", models.ImageField(blank=True, null=True, upload_to="delivery/licenses/")),
            ("bank_account_holder", models.CharField(blank=True, max_length=120)), ("bank_account_last4", models.CharField(blank=True, max_length=4)),
            ("bank_ifsc_code", models.CharField(blank=True, max_length=11)),
            ("status", models.CharField(choices=[("pending", "Pending verification"), ("approved", "Approved"), ("suspended", "Suspended"), ("rejected", "Rejected")], default="pending", max_length=20)),
            ("is_online", models.BooleanField(default=False)), ("verified_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_agent", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ("full_name",)}),
        migrations.CreateModel(name="LocalDelivery", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("pincode", models.CharField(db_index=True, max_length=6, validators=[django.core.validators.RegexValidator("^\\d{6}$", "Enter a valid 6-digit pincode.")])),
            ("pickup_name", models.CharField(max_length=150)), ("pickup_address", models.TextField()),
            ("customer_name", models.CharField(max_length=120)), ("customer_phone", models.CharField(max_length=15)),
            ("delivery_address", models.TextField()), ("delivery_fee", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
            ("agent_earning", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
            ("status", models.CharField(choices=[("available", "Available"), ("assigned", "Assigned"), ("accepted", "Accepted"), ("picked_up", "Picked up"), ("out_for_delivery", "Out for delivery"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="available", max_length=25)),
            ("delivery_otp_hash", models.CharField(blank=True, max_length=128)), ("otp_expires_at", models.DateTimeField(blank=True, null=True)),
            ("assigned_at", models.DateTimeField(blank=True, null=True)), ("picked_up_at", models.DateTimeField(blank=True, null=True)),
            ("delivered_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("agent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="deliveries", to="delivery.deliveryagentprofile")),
            ("food_order", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="local_delivery", to="food.foodorder")),
            ("grocery_order", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="local_delivery", to="groceries.groceryorder")),
        ], options={"ordering": ("-created_at",)}),
        migrations.AddConstraint(model_name="localdelivery", constraint=models.CheckConstraint(check=models.Q(models.Q(("food_order__isnull", True), ("grocery_order__isnull", False)), models.Q(("food_order__isnull", False), ("grocery_order__isnull", True)), _connector="OR"), name="delivery_exactly_one_order")),
        migrations.CreateModel(name="DeliveryEarning", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("amount", models.DecimalField(decimal_places=2, max_digits=8)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("payable", "Payable"), ("paid", "Paid")], default="payable", max_length=20)),
            ("paid_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("agent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="earnings", to="delivery.deliveryagentprofile")),
            ("delivery", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="earning", to="delivery.localdelivery")),
        ], options={"ordering": ("-created_at",)}),
    ]
