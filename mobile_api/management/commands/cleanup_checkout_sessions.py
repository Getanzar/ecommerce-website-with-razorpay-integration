from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from mobile_api.models import CheckoutSession


class Command(BaseCommand):
    help = "Delete expired, unfinished mobile checkout sessions."

    def add_arguments(self, parser):
        parser.add_argument("--retention-hours", type=int, default=24)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=max(options["retention_hours"], 0))
        deleted, _ = CheckoutSession.objects.filter(
            status="quoted", expires_at__lt=cutoff
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired checkout sessions."))
