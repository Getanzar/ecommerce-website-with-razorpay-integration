from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_sellerprofile_kyc_fields")]

    operations = [
        migrations.AddField(
            model_name="sellerprofile",
            name="ai_plan",
            field=models.CharField(blank=True, choices=[("", "No AI image plan"), ("starter", "Starter - 25 images"), ("growth", "Growth - 150 images"), ("pro", "Pro - 400 images")], max_length=20),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="ai_image_limit",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="ai_images_used",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="ai_subscription_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SellerAIPlanPurchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("razorpay_order_id", models.CharField(max_length=100, unique=True)),
                ("razorpay_payment_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("amount_paise", models.PositiveIntegerField()),
                ("plan_code", models.CharField(max_length=20)),
                ("image_limit", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("paid", "Paid")], default="pending", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_plan_purchases", to="accounts.sellerprofile")),
            ],
        ),
    ]
