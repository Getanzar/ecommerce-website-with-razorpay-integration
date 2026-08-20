# Generated manually for the marketplace seller foundation.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_sellerprofile"),
        ("products", "0017_category_background_image_category_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="seller",
            field=models.ForeignKey(
                blank=True,
                help_text="Leave empty for products sold directly by the marketplace.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="accounts.sellerprofile",
            ),
        ),
    ]
