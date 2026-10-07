from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("products", "0022_product_gender_product_kids_age_group")]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="kids_age_group",
            field=models.CharField(
                blank=True,
                choices=[
                    ("0-1", "0 - 1 Year"),
                    ("1-2", "1 - 2 Years"),
                    ("2-3", "2 - 3 Years"),
                    ("2-4", "2 - 4 Years"),
                    ("4-6", "4 - 6 Years"),
                    ("6-8", "6 - 8 Years"),
                    ("8-10", "8 - 10 Years"),
                    ("10-12", "10 - 12 Years"),
                    ("12-14", "12 - 14 Years"),
                ],
                db_index=True,
                default="",
                help_text="Age group for kids products. Leave blank for non-kids products.",
                max_length=10,
            ),
        ),
    ]
