from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_sellerprofile_payout_fields"), ("orders", "0023_returnrequest_order_item")]
    operations = [
        migrations.CreateModel(name="SellerSettlement", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("gross_amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("commission_amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("net_amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("payment_method", models.CharField(choices=[("online", "Online Payment"), ("cod", "Cash on Delivery")], max_length=20)),
            ("status", models.CharField(choices=[("scheduled", "Scheduled"), ("processing", "Processing"), ("paid", "Paid"), ("failed", "Failed"), ("on_hold", "On hold"), ("reversed", "Reversed")], default="scheduled", max_length=20)),
            ("scheduled_for", models.DateTimeField()), ("provider_payout_id", models.CharField(blank=True, max_length=100)),
            ("failure_reason", models.TextField(blank=True)), ("processed_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="seller_settlements", to="orders.order")),
            ("seller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="settlements", to="accounts.sellerprofile")),
        ], options={"ordering": ["-created_at"]}),
        migrations.AddConstraint(model_name="sellersettlement", constraint=models.UniqueConstraint(fields=("seller", "order"), name="one_settlement_per_seller_order")),
    ]
