import requests

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import SellerDeliveryCharge


class Command(BaseCommand):
    help = "Refresh every active per-seller Delhivery shipment. Run periodically."

    def handle(self, *args, **options):
        if not settings.DELHIVERY_API_KEY:
            self.stderr.write("DELHIVERY_API_KEY is not configured.")
            return
        charges = SellerDeliveryCharge.objects.filter(
            provider="delhivery",
        ).exclude(awb_number="").exclude(carrier_status__iexact="delivered").select_related("parcel_order")
        refreshed = 0
        for charge in charges.iterator():
            try:
                response = requests.get(
                    "https://track.delhivery.com/api/v1/packages/json/",
                    params={"waybill": charge.awb_number},
                    headers={"Authorization": f"Token {settings.DELHIVERY_API_KEY}"},
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                shipment = (payload.get("ShipmentData") or [{}])[0].get("Shipment", {})
                status = shipment.get("Status", {}).get("Status", "") or charge.carrier_status
                charge.carrier_status = status.lower() if status.lower() == "delivered" else status
                charge.manifestation_payload = {
                    **(charge.manifestation_payload or {}),
                    "latest_tracking": shipment,
                }
                charge.save(update_fields=["carrier_status", "manifestation_payload"])
                order = charge.parcel_order
                if order:
                    order.delivery_status = status
                    order.eta = shipment.get("ExpectedDeliveryDate") or shipment.get("EDD") or order.eta
                    if (
                        not order.sellerdeliverycharges.filter(provider="delhivery").exclude(carrier_status__iexact="delivered").exists()
                        and not order.local_deliveries.exclude(status="delivered").exists()
                    ):
                        order.status = "Delivered"
                        if not order.delivered_at:
                            order.delivered_at = timezone.now()
                    order.save(update_fields=["delivery_status", "eta", "status", "delivered_at"])
                refreshed += 1
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                self.stderr.write(f"AWB {charge.awb_number}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Refreshed {refreshed} Delhivery shipment(s)."))
