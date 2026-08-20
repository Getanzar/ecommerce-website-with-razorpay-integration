from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("orders", "0025_seller_return_debits")]
    operations = [
        migrations.AddField(model_name="orderitem", name="fulfillment_status", field=models.CharField(choices=[("new", "New"), ("accepted", "Accepted"), ("packed", "Packed"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="new", max_length=20)),
        migrations.AddField(model_name="orderitem", name="seller_tracking_number", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="orderitem", name="seller_courier", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="orderitem", name="fulfilled_at", field=models.DateTimeField(blank=True, null=True)),
    ]
