from django.db import migrations


def seed(apps, schema_editor):
    Category = apps.get_model("products", "Category")
    SubCategory = apps.get_model("products", "SubCategory")
    db = schema_editor.connection.alias
    category, _ = Category.objects.using(db).get_or_create(slug="electronics", defaults={"name": "Electronics"})
    for name in ("Mobiles", "TVs", "Laptops", "Home Appliances", "Mobile Accessories"):
        SubCategory.objects.using(db).get_or_create(category=category, name=name)


class Migration(migrations.Migration):
    dependencies = [("products", "0025_product_specifications_alter_product_product_type")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
