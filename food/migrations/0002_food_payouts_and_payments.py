from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_sellerprofile_payout_fields"), ("food", "0001_initial")]
    operations = [
        migrations.AddField(model_name="foodorder", name="razorpay_order_id", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="foodorder", name="razorpay_payment_id", field=models.CharField(blank=True, max_length=100)),
        migrations.CreateModel(name="FoodSellerSettlement", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("gross_amount", models.DecimalField(decimal_places=2, max_digits=12)), ("commission_amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("net_amount", models.DecimalField(decimal_places=2, max_digits=12)), ("deductions_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
            ("payment_method", models.CharField(max_length=10)), ("status", models.CharField(choices=[("scheduled", "Scheduled"), ("processing", "Processing"), ("paid", "Paid"), ("failed", "Failed"), ("offset", "Offset")], default="scheduled", max_length=20)),
            ("scheduled_for", models.DateTimeField()), ("provider_payout_id", models.CharField(blank=True, max_length=100)), ("failure_reason", models.TextField(blank=True)),
            ("processed_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="seller_settlement", to="food.foodorder")),
            ("seller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="food_settlements", to="accounts.sellerprofile")),
        ]),
    ]
