from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("groceries", "0008_grocery_product_pack_sizes")]
    operations = [migrations.AddField(
        model_name="groceryproduct", name="description", field=models.TextField(blank=True),
    )]
