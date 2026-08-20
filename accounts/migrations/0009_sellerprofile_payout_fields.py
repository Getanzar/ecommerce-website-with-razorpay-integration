from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_seller_ai_credits")]
    operations = [
        migrations.AddField(model_name="sellerprofile", name="payouts_enabled", field=models.BooleanField(default=False, help_text="Enable only after the seller bank account has been verified.")),
        migrations.AddField(model_name="sellerprofile", name="razorpay_contact_id", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="sellerprofile", name="razorpay_fund_account_id", field=models.CharField(blank=True, max_length=100)),
    ]
