from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_passwordresetotp")]

    operations = [
        migrations.AddField(model_name="sellerprofile", name="aadhaar_last4", field=models.CharField(blank=True, max_length=4)),
        migrations.AddField(model_name="sellerprofile", name="bank_account_holder", field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name="sellerprofile", name="bank_account_last4", field=models.CharField(blank=True, max_length=4)),
        migrations.AddField(model_name="sellerprofile", name="bank_ifsc_code", field=models.CharField(blank=True, max_length=11)),
        migrations.AddField(model_name="sellerprofile", name="business_category", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="sellerprofile", name="gstin", field=models.CharField(blank=True, max_length=15)),
        migrations.AddField(model_name="sellerprofile", name="legal_business_name", field=models.CharField(blank=True, max_length=150)),
    ]
