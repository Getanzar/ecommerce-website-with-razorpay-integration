from decimal import Decimal, ROUND_HALF_UP
import uuid

from django.db import migrations


def backfill_agent_fee(apps, schema_editor):
    DeliveryEarning = apps.get_model("delivery", "DeliveryEarning")
    rate = Decimal("10.00")
    for earning in DeliveryEarning.objects.all().iterator():
        gross = Decimal(earning.amount)
        fee = (gross * rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        earning.platform_fee_percent = rate
        earning.platform_fee_amount = fee
        earning.net_amount = gross - fee
        if not earning.payout_idempotency_key:
            earning.payout_idempotency_key = str(uuid.uuid4())
        earning.save(update_fields=[
            "platform_fee_percent", "platform_fee_amount", "net_amount",
            "payout_idempotency_key",
        ])


class Migration(migrations.Migration):
    dependencies = [("delivery", "0004_remove_localdelivery_delivery_exactly_one_order_and_more")]
    operations = [migrations.RunPython(backfill_agent_fee, migrations.RunPython.noop)]
