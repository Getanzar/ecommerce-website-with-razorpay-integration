from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("delivery", "0005_backfill_agent_fee")]
    operations = [migrations.AddField(
        model_name="localdelivery", name="delivery_otp_seed",
        field=models.CharField(max_length=64, blank=True, editable=False),
    )]
