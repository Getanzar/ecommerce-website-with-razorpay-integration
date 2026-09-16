from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("food", "0005_foodsellersettlement_delivery_charge_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="FoodCartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("option", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cart_items", to="food.menuitemoption")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="food_cart_items", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="foodcartitem", constraint=models.UniqueConstraint(fields=("user", "option"), name="unique_mobile_food_cart_option")),
    ]
