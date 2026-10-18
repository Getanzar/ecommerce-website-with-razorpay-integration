"""Read-only deployment check. Never prints credentials or generates paid content."""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from dashboard.listing_assistant import ListingAssistantError, gemini_config
from dashboard.models import SellerListingAIUsage


class Command(BaseCommand):
    help = "Check Gemini settings and the usage table; optionally verify model access without generating a listing."

    def add_arguments(self, parser):
        parser.add_argument("--verify-provider", action="store_true", help="Read the Gemini model metadata using the configured API key. No generation request is made.")

    def handle(self, *args, **options):
        try:
            key, model = gemini_config()
        except ListingAssistantError as exc:
            raise CommandError(str(exc)) from None
        if SellerListingAIUsage._meta.db_table not in connection.introspection.table_names():
            raise CommandError("Listing usage table is missing. Run python manage.py migrate --noinput first.")
        self.stdout.write(f"Provider: Google Gemini; model: {model}; key: configured (hidden)")
        self.stdout.write(f"Daily attempts per seller: {settings.SELLER_LISTING_AI_DAILY_LIMIT}")
        if options["verify_provider"]:
            try:
                response = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models/{model}",
                    headers={"x-goog-api-key": key}, timeout=(5, 15))
                if response.status_code == 429:
                    raise CommandError("Google quota/rate limit reached. Check this project's limits in AI Studio.")
                if not response.ok:
                    raise CommandError(f"Gemini model access check failed (HTTP {response.status_code}). Check the API key, project, model access and billing in AI Studio.")
                if "generateContent" not in response.json().get("supportedGenerationMethods", []):
                    raise CommandError("The configured model does not advertise generateContent support.")
            except (requests.RequestException, ValueError):
                raise CommandError("Could not read Gemini model metadata. Check network access and provider status.") from None
            self.stdout.write(self.style.SUCCESS("Gemini key and model access verified. No listing generated."))
        self.stdout.write(self.style.SUCCESS("Listing assistant configuration checks passed for the shared website/mobile backend."))
