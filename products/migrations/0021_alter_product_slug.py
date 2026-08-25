from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0020_product_gst_rate_product_package_height_cm_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="slug",
            field=models.SlugField(max_length=255, unique=True),
        ),
    ]
