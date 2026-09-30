from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from food.models import Restaurant
from groceries.models import GroceryStore


class SellerCategoryAccessTests(APITestCase):
    def test_free_text_category_cannot_change_authorization(self):
        self.seller.business_category = "Restaurant and Grocery"
        self.seller.save()
        self.assertEqual(self.client.get("/api/v1/partners/seller/").data["allowed_kinds"], ["shop"])
        self.assertEqual(self.client.get("/api/v1/partners/seller/food/catalog/").status_code, 403)

    def test_registration_schema_requires_validated_segment_choice(self):
        from accounts.forms import SellerApplicationForm
        from django.core.exceptions import ValidationError
        field = SellerApplicationForm().fields["business_segment"]
        self.assertTrue(field.required)
        self.assertEqual(field.clean("food"), "food")
        with self.assertRaises(ValidationError):
            field.clean("bakery")

    def test_backfill_preserves_labels_and_leaves_unknown_for_review(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from types import SimpleNamespace
        migration = import_module("accounts.migrations.0012_sellerprofile_business_segment")
        for label, expected in ((" Restaurant ", "food"), ("Kirana Store", "grocery"), ("Clothes", "shop"), ("bakery", ""), ("Food and Grocery", "")):
            SellerProfile.objects.filter(pk=self.seller.pk).update(business_category=label, business_segment="")
            migration.backfill_segments(apps, SimpleNamespace(connection=connection))
            self.seller.refresh_from_db()
            self.assertEqual(self.seller.business_category, label)
            self.assertEqual(self.seller.business_segment, expected)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("category-seller")
        self.seller = SellerProfile.objects.create(
            user=self.user, store_name="Category store", status="approved",
            business_segment="shop", business_category="Clothes",
        )
        self.client.force_authenticate(self.user)

    def test_registered_category_controls_workspace_and_all_other_tools(self):
        Restaurant.objects.create(seller=self.seller, name="Old kitchen")
        GroceryStore.objects.create(seller=self.seller, name="Old grocer")
        for category, allowed in (("Clothes", "shop"), ("Restaurant", "food"),
                                  ("Groceries", "grocery"), ("Kirana", "grocery")):
            with self.subTest(category=category):
                cache.clear()
                self.seller.business_segment = allowed
                self.seller.business_category = category
                self.seller.save()
                workspace = self.client.get("/api/v1/partners/seller/").data
                self.assertEqual(workspace["allowed_kinds"], [allowed])
                self.assertEqual(workspace["business_category"], category)
                self.assertTrue(all(s["kind"] == allowed for s in workspace["stores"]))
                for kind in ("shop", "food", "grocery"):
                    prefix = f"/api/v1/partners/seller/{kind}/"
                    for endpoint in ("orders/", "catalog/", "payouts/"):
                        self.assertEqual(self.client.get(prefix + endpoint).status_code,
                                         200 if kind == allowed else 403)
                    if kind == allowed:
                        continue
                    for method, endpoint in (("patch", "availability/"),
                                             ("get", "store/"), ("post", "store/"),
                                             ("post", "products/new/"),
                                             ("get", "products/1/edit/"),
                                             ("patch", "catalog/1/"),
                                             ("patch", "orders/1/"),
                                             ("post", "products/1/variants/new/"),
                                             ("post", "orders/1/cases/")):
                        self.assertEqual(getattr(self.client, method)(prefix + endpoint).status_code, 403)
                if allowed != "shop":
                    for endpoint in ("categories/", "products/new/", "products/1/edit/", "products/1/colors/"):
                        self.assertEqual(self.client.get("/api/v1/partners/seller/" + endpoint).status_code, 403)

    def test_missing_category_keeps_shared_setup_but_denies_category_access(self):
        self.seller.business_segment = ''
        self.seller.business_category = " "
        self.seller.save()
        response = self.client.get("/api/v1/partners/seller/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["allowed_kinds"], [])
        self.assertEqual(self.client.get("/api/v1/partners/payout-setup/seller/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/partners/seller/shop/catalog/").status_code, 403)
