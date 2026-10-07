from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("products", "0023_alter_product_kids_age_group")]
    operations = [migrations.AlterField(
        model_name="product", name="kids_age_group",
        field=models.CharField(blank=True, choices=[
        ("0-1", "0 - 1 Year"),
        ("1-2", "1 - 2 Years"),
        ("2-3", "2 - 3 Years"),
        ("3-4", "3 - 4 Years"),
        ("4-5", "4 - 5 Years"),
        ("5-6", "5 - 6 Years"),
        ("6-7", "6 - 7 Years"),
        ("7-8", "7 - 8 Years"),
        ("8-9", "8 - 9 Years"),
        ("9-10", "9 - 10 Years"),
        ("10-11", "10 - 11 Years"),
        ("11-12", "11 - 12 Years"),
        ("12-13", "12 - 13 Years"),
        ("13-14", "13 - 14 Years"),
        ("14-15", "14 - 15 Years"),
        ("2-4", "2 - 4 Years"),
        ("4-6", "4 - 6 Years"),
        ("6-8", "6 - 8 Years"),
        ("8-10", "8 - 10 Years"),
        ("10-12", "10 - 12 Years"),
        ("12-14", "12 - 14 Years"),
    ],
            db_index=True, default="", max_length=10,
            help_text="Age group for kids products. Leave blank for non-kids products."),
    )]
