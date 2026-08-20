from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0008_seller_ai_credits"),
        ("products", "0018_product_seller"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="moderation_status",
            field=models.CharField(choices=[("pending", "Pending review"), ("approved", "Approved"), ("rejected", "Rejected")], db_index=True, default="approved", max_length=20),
        ),
        migrations.AddField(
            model_name="product",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="product",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_products", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="CatalogRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_type", models.CharField(choices=[("category", "Category"), ("subcategory", "Subcategory")], max_length=20)),
                ("name", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending review"), ("approved", "Approved"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=20)),
                ("admin_note", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("parent_category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="subcategory_requests", to="products.category")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_catalog_requests", to=settings.AUTH_USER_MODEL)),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="catalog_requests", to="accounts.sellerprofile")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
