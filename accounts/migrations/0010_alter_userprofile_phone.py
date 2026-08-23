from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_sellerprofile_payout_fields")]

    operations = [
        migrations.AddConstraint(
            model_name="userprofile",
            constraint=models.UniqueConstraint(
                condition=~models.Q(phone=""),
                fields=("phone",),
                name="unique_nonempty_user_phone",
            ),
        ),
    ]
