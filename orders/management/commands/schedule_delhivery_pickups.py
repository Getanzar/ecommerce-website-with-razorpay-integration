from django.core.management.base import BaseCommand
from orders.pickups import parcel_ready, schedule_charge_pickup
from payments.models import SellerDeliveryCharge


class Command(BaseCommand):
    help = "Catch up packed Delhivery parcels; uncertain carrier attempts are never duplicated."

    def add_arguments(self, parser):
        parser.add_argument("--retry-failed", action="store_true")

    def handle(self, *args, **options):
        charges = SellerDeliveryCharge.objects.filter(provider="delhivery", parcel_order__isnull=False).select_related("parcel_order", "seller")
        for charge in charges.iterator():
            if not parcel_ready(charge):
                continue
            try:
                pickup = schedule_charge_pickup(charge.pk, retry=options["retry_failed"])
                self.stdout.write(f"Package {charge.pk}: {pickup.status if pickup else 'shipment setup required'}")
            except Exception as exc:
                SellerDeliveryCharge.objects.filter(pk=charge.pk).update(pickup_error=str(exc)[:1000])
                self.stderr.write(f"Package {charge.pk}: {exc}")
