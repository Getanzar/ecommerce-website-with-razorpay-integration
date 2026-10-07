from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check payment/delivery launch configuration without contacting providers or revealing keys."

    def handle(self, *args, **options):
        blockers = []
        for name in (
            "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET",
            "DELHIVERY_API_KEY", "DELHIVERY_PICKUP_LOCATION",
            "RAZORPAYX_KEY_ID", "RAZORPAYX_KEY_SECRET", "RAZORPAYX_ACCOUNT_NUMBER",
            "RAZORPAYX_WEBHOOK_SECRET", "BREVO_API_KEY", "BREVO_SENDER_EMAIL",
        ):
            if not getattr(settings, name, ""):
                blockers.append(f"{name} is missing")
        if not (settings.RAZORPAY_KEY_ID or "").startswith("rzp_live_"):
            blockers.append("Customer payments do not use a live Razorpay key")
        if settings.DEBUG:
            blockers.append("DEBUG is enabled")
        if not settings.SECURE_SSL_REDIRECT:
            blockers.append("HTTPS redirect is disabled")
        if not settings.DELHIVERY_REQUIRE_LIVE_QUOTE:
            blockers.append("Delhivery fallback quotes are enabled; set DELHIVERY_REQUIRE_LIVE_QUOTE=True")
        for problem in blockers:
            self.stderr.write(f"BLOCKER: {problem}")
        self.stdout.write(
            "Still verify on production: migrations, public webhooks and refunds, registered seller pickup names, "
            "serviceable destinations, pickup requests/labels, approved online riders and delivery OTP email, "
            "COD remittances, payout accounts, scheduled booking/tracking/push/payout jobs, and a physical pilot delivery."
        )
        if blockers:
            raise CommandError(f"{len(blockers)} configuration blocker(s). Not launch ready.")
        self.stdout.write(self.style.SUCCESS("Configuration checks passed. Live operational acceptance is still required."))
