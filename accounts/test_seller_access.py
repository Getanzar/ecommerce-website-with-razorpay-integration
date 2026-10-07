from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import SellerProfile


class SellerWorkspaceEntryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("existing-seller")
        self.seller = SellerProfile.objects.create(user=self.user, store_name="Existing store", status="approved")
        self.client.force_login(self.user)

    def test_approved_legacy_seller_sees_profile_without_redirect_loop(self):
        response = self.client.get(reverse("seller_application"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your selling segment needs to be assigned")
        response = self.client.get(reverse("seller_dashboard"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertEqual(self.client.get(reverse("seller_products")).status_code, 403)
        self.client.post(reverse("seller_application"), {"business_segment": "shop", "status": "approved"})
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.business_segment, "")
        self.assertEqual(self.seller.status, "approved")

    def test_approved_merchandise_seller_opens_existing_workspace(self):
        self.seller.business_segment = "shop"
        self.seller.save()
        response = self.client.get(reverse("seller_application"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/seller/dashboard.html")
        self.assertEqual(SellerProfile.objects.filter(user=self.user).count(), 1)

    def test_pending_seller_opens_application_status(self):
        self.seller.status = "pending"
        self.seller.save()
        response = self.client.get(reverse("seller_dashboard"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "awaiting marketplace approval")
        self.assertEqual(self.client.get(reverse("seller_products")).status_code, 403)

    def test_non_seller_enters_registration_from_workspace_link(self):
        self.seller.delete()
        response = self.client.get(reverse("seller_dashboard"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/seller_application.html")
