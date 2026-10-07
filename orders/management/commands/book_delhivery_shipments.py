from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from payments.models import SellerDeliveryCharge
from orders.shipping import manifest_delhivery_shipments


class Command(BaseCommand):
    help = "Book unattempted paid/COD parcel shipments. Reconcile ambiguous failures with Delhivery before retrying."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not settings.DELHIVERY_API_KEY and not options["dry_run"]:
            raise CommandError("DELHIVERY_API_KEY is not configured.")
        charges = SellerDeliveryCharge.objects.filter(
            provider="delhivery", awb_number="",
            carrier_status__in=["", "quoted", "quote_only", "pickup_registration_required"],
            parcel_order__isnull=False,
        ).select_related("parcel_order", "seller")
        for charge in charges.iterator():
            order = charge.parcel_order
            if order.status in {"Cancelled", "Returned", "Delivered"}:
                continue
            if order.payment_method != "cod" and order.payment_status != "Paid":
                continue
            if options["dry_run"]:
                self.stdout.write(f"Order {order.pk}, package {charge.pk}: eligible")
                continue
            booked = manifest_delhivery_shipments(order, [charge])[0]
            self.stdout.write(f"Order {order.pk}, package {charge.pk}: {booked.carrier_status}")
        unresolved = SellerDeliveryCharge.objects.filter(
            provider="delhivery", awb_number="",
            carrier_status__in=["manifestation_failed", "manifestation_pending"],
        ).count()
        if unresolved:
            self.stderr.write(f"{unresolved} package(s) need carrier reconciliation; no automatic retry was sent.")
