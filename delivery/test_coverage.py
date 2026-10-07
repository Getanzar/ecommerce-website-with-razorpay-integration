from unittest.mock import patch
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import SellerProfile
from delivery.coverage import has_local_coverage
from delivery.models import DeliveryAgentProfile, DeliveryZone
from payments.pricing import build_parcel_pricing


class SellerCoverageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("coverage-seller")
        self.seller = SellerProfile.objects.create(
            user=self.owner, store_name="Coverage store", status="approved",
            business_pincode="243638", business_address="Market Road",
            business_latitude="28.073100", business_longitude="78.750200",
        )
        self.rider_user = User.objects.create_user("coverage-rider")
        self.rider = DeliveryAgentProfile.objects.create(
            user=self.rider_user, status="pending", pincode="243638", is_online=True,
        )

    def test_only_approved_active_accounts_cover_enabled_areas(self):
        self.assertFalse(has_local_coverage("243638"))
        self.rider.status = "approved"
        self.rider.is_online = False
        self.rider.save()
        self.assertTrue(has_local_coverage("243638"))
        self.assertFalse(has_local_coverage("110001"))
        self.rider_user.is_active = False
        self.rider_user.save()
        self.assertFalse(has_local_coverage("243638"))
        self.rider_user.is_active = True
        self.rider_user.save()
        DeliveryZone.objects.create(pincode="243638", city="Town", is_active=False)
        self.assertFalse(has_local_coverage("243638"))

    @patch("payments.pricing.chargeable_weight_grams", return_value=500)
    @patch("payments.pricing.quote_delhivery")
    @patch("payments.pricing.quote_local_delivery")
    def test_same_pincode_without_riders_uses_courier(self, local, courier, weight):
        quote = {"provider": "delhivery", "quoted_total": Decimal("40"), "tax_amount": Decimal("0")}
        courier.return_value = quote.copy()
        local.return_value = {**quote, "provider": "local"}
        items = [{"product": SimpleNamespace(seller=self.seller, gst_rate=Decimal("5")),
                  "variant": SimpleNamespace(seller_price=Decimal("100"), final_price=Decimal("110")), "quantity": 1}]
        destination = {"pincode": "243638", "latitude": "28.074", "longitude": "78.751"}
        _, quotes = build_parcel_pricing(items, destination, "cod")
        self.assertEqual(quotes[0]["provider"], "delhivery")
        local.assert_not_called()
        self.rider.status = "approved"
        self.rider.save()
        _, quotes = build_parcel_pricing(items, destination, "cod")
        self.assertEqual(quotes[0]["provider"], "local")

    def test_coverage_dashboard_is_protected_and_searchable(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("ops_seller_coverage")).status_code, 403)
        admin = User.objects.create_superuser("coverage-admin", "admin@example.com", "password")
        self.client.force_login(admin)
        response = self.client.get(reverse("ops_seller_coverage"), {"q": "243638", "coverage": "missing"})
        self.assertContains(response, "Coverage store")
        self.assertContains(response, "No approved riders")
        self.assertContains(self.client.get(reverse("admin_dashboard")), "Seller areas")
        self.rider.status = "approved"
        self.rider.save()
        response = self.client.get(reverse("ops_seller_coverage"), {"coverage": "online"})
        self.assertContains(response, "Riders online")
