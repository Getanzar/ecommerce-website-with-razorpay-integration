from django.db import migrations
from django.utils.text import slugify


def seed_categories(apps, schema_editor):
    Category = apps.get_model("groceries", "GroceryCategory")
    names = [
        "Fruits & Vegetables", "Dairy & Breakfast", "Atta, Rice & Dal",
        "Snacks & Beverages", "Masala & Cooking", "Personal Care",
        "Household Care", "Baby Care",
    ]
    for order, name in enumerate(names):
        Category.objects.get_or_create(name=name, defaults={"slug": slugify(name), "display_order": order})


class Migration(migrations.Migration):
    dependencies = [("groceries", "0001_initial")]
    operations = [migrations.RunPython(seed_categories, migrations.RunPython.noop)]
