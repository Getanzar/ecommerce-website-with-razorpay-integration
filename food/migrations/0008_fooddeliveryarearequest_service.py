from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("food", "0007_fooddeliveryarearequest")]

    operations = [
        migrations.AddField(
            model_name="fooddeliveryarearequest",
            name="service",
            field=models.CharField(choices=[("food", "Food"), ("grocery", "Groceries")], default="food", max_length=10),
        ),
    ]
