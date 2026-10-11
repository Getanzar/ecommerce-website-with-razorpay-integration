from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from delivery.collection import CollectionError, provider, reconcile_qr
from delivery.models import DeliveryCollection


class Command(BaseCommand):
    help = "Attach a verified Razorpay QR to a delivery after an uncertain creation response."

    def add_arguments(self, parser):
        parser.add_argument("--delivery-id", type=int, required=True)
        parser.add_argument("--qr-id", required=True)

    def handle(self, **options):
        try:
            qr = provider("GET", f"/payments/qr_codes/{options['qr_id']}")
            with transaction.atomic():
                record = DeliveryCollection.objects.select_for_update().get(delivery_id=options["delivery_id"])
                if record.status != "issuing":
                    raise CommandError("Only a delivery awaiting QR reconciliation can be updated.")
                if (qr.get("notes", {}).get("delivery_id") != str(record.delivery_id)
                        or qr.get("payment_amount") != int(record.amount * 100)
                        or qr.get("usage") != "single_use" or qr.get("fixed_amount") is not True
                        or qr.get("type") != "upi_qr" or qr.get("id") != options["qr_id"]
                        or not str(qr.get("image_url", "")).startswith("https://")):
                    raise CommandError("The QR does not match this delivery and amount.")
                record.qr_id, record.qr_image_url, record.status = qr["id"], qr["image_url"], "pending"
                record.save(update_fields=["qr_id", "qr_image_url", "status", "updated_at"])
            reconcile_qr(qr["id"])
        except (CollectionError, DeliveryCollection.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Delivery QR reconciled. Refresh the delivery payment page."))
