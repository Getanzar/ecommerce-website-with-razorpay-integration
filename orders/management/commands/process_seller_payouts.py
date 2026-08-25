from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order, SellerSettlement
from orders.settlements import apply_return_debits, create_settlements_for_order, fetch_razorpayx_payout, submit_razorpayx_payout


class Command(BaseCommand):
    help = "Submit all due seller settlements to RazorpayX. Run every morning via cron."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from delivery.models import DeliveryEarning
        from delivery.payouts import submit_agent_payout
        from food.models import FoodOrder, FoodSellerSettlement
        from food.settlements import create_food_settlement
        from groceries.models import GroceryOrder, GrocerySellerSettlement
        from groceries.settlements import create_grocery_settlement
        eligible_orders = Order.objects.filter(payment_status="Paid").exclude(
            status__in=["Cancelled", "Returned"]
        )
        for order in eligible_orders.iterator():
            create_settlements_for_order(order)
        for order in FoodOrder.objects.filter(payment_status="Paid").exclude(status="cancelled").iterator():
            create_food_settlement(order)
        for order in GroceryOrder.objects.filter(payment_status="Paid").exclude(status="cancelled").iterator():
            create_grocery_settlement(order)
        due = list(SellerSettlement.objects.filter(
            status__in=["scheduled", "failed"], scheduled_for__lte=timezone.now()
        ).select_related("seller", "order")) + list(FoodSellerSettlement.objects.filter(
            status__in=["scheduled", "failed"], scheduled_for__lte=timezone.now()
        ).select_related("seller", "order")) + list(GrocerySellerSettlement.objects.filter(
            status__in=["scheduled", "failed"], scheduled_for__lte=timezone.now()
        ).select_related("seller", "order"))
        self.stdout.write(f"Found {len(due)} due settlement(s).")
        if options["dry_run"]:
            return
        processing = list(SellerSettlement.objects.filter(status="processing").exclude(provider_payout_id="")) + list(FoodSellerSettlement.objects.filter(status="processing").exclude(provider_payout_id="")) + list(GrocerySellerSettlement.objects.filter(status="processing").exclude(provider_payout_id=""))
        for settlement in processing:
            try:
                provider = fetch_razorpayx_payout(settlement.provider_payout_id)
                if provider.get("status") == "processed":
                    settlement.status = "paid"
                    settlement.processed_at = timezone.now()
                    settlement.save(update_fields=["status", "processed_at", "updated_at"])
                elif provider.get("status") in {"rejected", "cancelled", "reversed"}:
                    settlement.status = "failed"
                    settlement.failure_reason = provider.get("failure_reason") or provider.get("status", "Payout failed")
                    settlement.save(update_fields=["status", "failure_reason", "updated_at"])
            except Exception as exc:
                self.stderr.write(f"Could not refresh settlement {settlement.pk}: {exc}")
        for earning in DeliveryEarning.objects.filter(status="processing").exclude(provider_payout_id=""):
            try:
                provider = fetch_razorpayx_payout(earning.provider_payout_id)
                if provider.get("status") == "processed":
                    earning.status = "paid"
                    earning.paid_at = timezone.now()
                    earning.failure_reason = ""
                    earning.save(update_fields=["status", "paid_at", "failure_reason"])
                elif provider.get("status") in {"rejected", "cancelled", "reversed"}:
                    earning.status = "failed"
                    earning.failure_reason = provider.get("failure_reason") or provider.get("status", "Payout failed")
                    earning.save(update_fields=["status", "failure_reason"])
            except Exception as exc:
                self.stderr.write(f"Could not refresh delivery earning {earning.pk}: {exc}")
        for settlement in due:
            settlement.status = "processing"
            settlement.failure_reason = ""
            settlement.save(update_fields=["status", "failure_reason", "updated_at"])
            try:
                if apply_return_debits(settlement) <= 0:
                    settlement.status = "offset"
                    settlement.processed_at = timezone.now()
                    settlement.save(update_fields=["status", "processed_at", "updated_at"])
                    self.stdout.write(self.style.SUCCESS(f"Offset settlement {settlement.pk} against returns."))
                    continue
                provider = submit_razorpayx_payout(settlement)
                settlement.provider_payout_id = provider["id"]
                if provider.get("status") == "processed":
                    settlement.status = "paid"
                    settlement.processed_at = timezone.now()
                settlement.save(update_fields=["provider_payout_id", "status", "processed_at", "updated_at"])
                self.stdout.write(self.style.SUCCESS(f"Submitted settlement {settlement.pk}."))
            except Exception as exc:
                settlement.status = "failed"
                settlement.failure_reason = str(exc)[:1000]
                settlement.save(update_fields=["status", "failure_reason", "updated_at"])
                self.stderr.write(f"Settlement {settlement.pk} failed: {exc}")

        agent_due = DeliveryEarning.objects.filter(
            status__in=["payable", "failed"], scheduled_for__lte=timezone.now(),
            agent__payouts_enabled=True,
        ).select_related("agent", "delivery")
        for earning in agent_due:
            earning.status = "processing"
            earning.failure_reason = ""
            earning.save(update_fields=["status", "failure_reason"])
            try:
                provider = submit_agent_payout(earning)
                earning.provider_payout_id = provider["id"]
                if provider.get("status") == "processed":
                    earning.status = "paid"
                    earning.paid_at = timezone.now()
                earning.save(update_fields=["provider_payout_id", "status", "paid_at"])
                self.stdout.write(self.style.SUCCESS(f"Submitted delivery earning {earning.pk}."))
            except Exception as exc:
                earning.status = "failed"
                earning.failure_reason = str(exc)[:1000]
                earning.save(update_fields=["status", "failure_reason"])
                self.stderr.write(f"Delivery earning {earning.pk} failed: {exc}")
