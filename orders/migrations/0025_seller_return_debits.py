from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("orders", "0024_sellersettlement")]
    operations = [
        migrations.AddField(model_name="sellersettlement", name="deductions_amount", field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.AlterField(model_name="sellersettlement", name="status", field=models.CharField(choices=[("scheduled", "Scheduled"), ("processing", "Processing"), ("paid", "Paid"), ("failed", "Failed"), ("on_hold", "On hold"), ("reversed", "Reversed"), ("offset", "Offset against return")], default="scheduled", max_length=20)),
        migrations.CreateModel(name="SellerReturnDebit", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("original_amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("remaining_amount", models.DecimalField(decimal_places=2, max_digits=12)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("return_request", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="seller_debit", to="orders.returnrequest")),
            ("seller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_debits", to="accounts.sellerprofile")),
        ]),
        migrations.CreateModel(name="SellerNotification", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("kind", models.CharField(default="return_balance_due", max_length=40)),
            ("title", models.CharField(max_length=150)), ("message", models.TextField()),
            ("is_read", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("seller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="accounts.sellerprofile")),
        ], options={"ordering": ["-created_at"]}),
    ]
