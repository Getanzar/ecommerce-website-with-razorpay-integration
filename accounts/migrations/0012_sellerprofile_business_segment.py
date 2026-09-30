from django.db import migrations, models


def backfill_segments(apps, schema_editor):
    # Deliberately conservative. Preserve original category text. Unknown or
    # mixed descriptions (including bakery) require an explicit admin decision.
    mapping = {
        "shop": "shop", "merchandise": "shop", "clothing": "shop",
        "clothes": "shop", "garments": "shop", "fashion": "shop",
        "electronics": "shop", "home decor": "shop",
        "food": "food", "restaurant": "food",
        "grocery": "grocery", "groceries": "grocery", "kirana": "grocery",
        "kirana store": "grocery", "supermarket": "grocery",
    }
    Seller = apps.get_model("accounts", "SellerProfile")
    for seller in Seller.objects.using(schema_editor.connection.alias).all().iterator():
        segment = mapping.get(seller.business_category.strip().lower(), "")
        if segment:
            Seller.objects.using(schema_editor.connection.alias).filter(pk=seller.pk).update(business_segment=segment)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_sellerprofile_business_gps_accuracy_meters_and_more")]
    operations = [
        migrations.AddField(
            model_name="sellerprofile", name="business_segment",
            field=models.CharField(blank=True, choices=[("shop", "Merchandise"), ("food", "Food / restaurant"), ("grocery", "Grocery / kirana")], default="", max_length=10,
                                   help_text="Select the approved selling segment. Blank legacy records require review; category descriptions never grant access."),
        ),
        migrations.RunPython(backfill_segments, migrations.RunPython.noop),
    ]
