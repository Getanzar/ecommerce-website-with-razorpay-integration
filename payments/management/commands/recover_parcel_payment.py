import razorpay
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from orders.commerce import finalize_parcel_transaction
from payments.models import PaymentTransaction


class Command(BaseCommand):
    help = "Verify a captured Razorpay parcel payment and recover its missing order. Defaults to inspection."

    def add_arguments(self, parser):
        parser.add_argument("provider_order_id")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        payment = PaymentTransaction.objects.get(
            provider="razorpay", channel_name="parcel",
            provider_order_id=options["provider_order_id"],
        )
        if payment.parcel_order_id:
            self.stdout.write(f"Already linked to order {payment.parcel_order_id}; no changes.")
            return
        if payment.status in {"refunded", "partially_refunded"} or payment.refunds.exclude(status="failed").exists():
            raise CommandError("Refund exists; reconcile it before recovering this order.")
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        entities = client.order.payments(payment.provider_order_id, timeout=15).get("items", [])
        captured = [entity for entity in entities if entity.get("status") == "captured"]
        if len(captured) != 1:
            raise CommandError("Expected exactly one captured payment; no changes made.")
        entity = captured[0]
        if (entity.get("order_id") != payment.provider_order_id
                or entity.get("amount") != int(payment.amount * 100)
                or entity.get("currency") != payment.currency
                or entity.get("amount_refunded", 0)
                or entity.get("refund_status")
                or (payment.provider_payment_id and payment.provider_payment_id != entity["id"])):
            raise CommandError("Provider payment mismatch or refund detected; no changes made.")
        self.stdout.write(f"Verified {entity['id']}: captured {payment.amount} {payment.currency}.")
        if not options["apply"]:
            self.stdout.write("Inspection only. Use --apply to create the order and start fulfilment.")
            return
        order = finalize_parcel_transaction(payment, entity["id"])
        self.stdout.write(f"Recovered order {order.pk}: {order.payment_status}.")
        for charge in order.sellerdeliverycharges.all():
            self.stdout.write(f"Package {charge.pk}: {charge.provider}, {charge.carrier_status}, AWB={charge.awb_number}")
