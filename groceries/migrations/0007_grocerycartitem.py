from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("groceries", "0006_groceryorder_razorpay_order_id_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="GroceryCartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cart_items", to="groceries.groceryproduct")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="grocery_cart_items", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="grocerycartitem", constraint=models.UniqueConstraint(fields=("user", "product"), name="unique_mobile_grocery_cart_product")),
    ]
