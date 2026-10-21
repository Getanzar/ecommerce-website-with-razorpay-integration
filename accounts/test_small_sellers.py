from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import SellerApplicationForm, SmallSellerApplicationForm
from accounts.models import SellerProfile
from accounts.seller_profile import SellerProfileForm
from dashboard.forms import SellerProductForm
from orders.models import Order, OrderItem
from orders.settlements import create_settlements_for_order
from payments.pricing import DeliveryQuoteError, build_parcel_pricing
from products.catalog import public_products
from products.models import Category, Product, ProductColor, ProductVariant


@override_settings(SECURE_SSL_REDIRECT=False, PLATFORM_FEE_GST_PERCENT="18.00", LOCAL_DELIVERY_BASE_FEE="30.00")
class SmallSellerFlowTests(TestCase):
    def setUp(self):
        self.identity_dir = TemporaryDirectory(dir=".")
        self.addCleanup(self.identity_dir.cleanup)
        storage = SellerProfile._meta.get_field("aadhaar_image").storage
        self.storage_override = patch.object(storage, "_location", self.identity_dir.name)
        self.storage_override.start()
        self.addCleanup(self.storage_override.stop)
        storage.__dict__.pop("location", None)
        storage.__dict__.pop("base_location", None)
        self.user = User.objects.create_user("small-seller")
        self.reviewer = User.objects.create_superuser("small-reviewer", "reviewer@example.com", "test-password")
        self.client.force_login(self.user)

    def image(self):
        output = BytesIO()
        Image.new("RGB", (30, 20), "white").save(output, format="PNG")
        return SimpleUploadedFile("masked.png", output.getvalue(), content_type="image/png")

    def small_form(self, data, **kwargs):
        return SmallSellerApplicationForm(data, {"aadhaar_image": data.get("aadhaar_image", self.image())}, **kwargs)

    def payload(self, **changes):
        data = {"store_name": "Local crafts", "legal_business_name": "Test Seller", "business_category": "Handmade goods", "business_segment": "shop", "business_phone": "9999999999", "business_address": "Local market", "business_pincode": "243638", "business_latitude": "28.073100", "business_longitude": "78.750200", "business_gps_accuracy_meters": "10", "gps_captured_at": timezone.now().isoformat(), "aadhaar_last4": "1234", "bank_account_holder": "Test Seller", "bank_account_number": "123456789012", "bank_ifsc_code": "SBIN0001234", "aadhaar_consent": "on", "eligibility_declaration": "on"}
        return {**data, "aadhaar_image": self.image(), **changes}

    def apply(self):
        response = self.client.post(reverse("small_seller_application"), self.payload())
        self.assertEqual(response.status_code, 302)
        return SellerProfile.objects.get(user=self.user)

    def verify(self, seller):
        self.client.force_login(self.reviewer)
        response = self.client.post(reverse("review_small_seller", args=[seller.pk]), {"decision": "verified", "identity_checked": "on", "eligibility_checked": "on", "reference": "REVIEW-SMALL-001"})
        self.assertEqual(response.status_code, 302)
        seller.refresh_from_db()
        return seller

    def approve(self, seller):
        self.verify(seller)
        self.client.post(reverse("update_seller_status", args=[seller.pk]), {"status": "approved"})
        seller.refresh_from_db()
        self.assertTrue(seller.is_approved)
        return seller

    def product(self, seller):
        category = Category.objects.create(name="Crafts", slug="small-crafts")
        product = Product.objects.create(seller=seller, category=category, name="Handmade bag", price=100, gst_rate=18, is_active=True, moderation_status="approved")
        color = ProductColor.objects.create(product=product, name="Natural")
        variant = ProductVariant.objects.create(product=product, color=color, size="Free", stock=5)
        return product, variant

    def test_sell_with_us_exposes_both_options_before_login(self):
        self.client.logout()
        response = self.client.get(reverse("seller_application"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "without GSTIN")
        self.assertContains(response, reverse("small_seller_application"))
        self.assertContains(response, reverse("registered_seller_application"))
        self.assertEqual(self.client.get(reverse("small_seller_application")).status_code, 302)

    def test_all_small_seller_segments_register_and_approve_without_pan_or_enrolment(self):
        for segment in ("shop", "food", "grocery"):
            with self.subTest(segment=segment):
                user = User.objects.create_user("small-" + segment)
                self.client.force_login(user)
                url = reverse("small_seller_application" if segment == "shop" else "small_" + segment + "_seller_application")
                response = self.client.get(url)
                self.assertContains(response, 'name="business_segment" value="' + segment + '"')
                self.assertNotContains(response, 'name="gstin"')
                self.assertNotContains(response, 'name="pan_number"')
                self.assertNotContains(response, 'name="gst_enrolment_number"')
                response = self.client.post(url, self.payload(store_name="Local " + segment, business_segment=segment))
                self.assertEqual(response.status_code, 302)
                seller = SellerProfile.objects.get(user=user)
                self.assertEqual(seller.business_segment, segment)
                self.assertEqual(seller.gstin, "")
                self.assertEqual(seller.pan_last4, "")
                self.assertEqual(seller.gst_enrolment_number, "")
                self.assertFalse(seller.is_approved)
                self.approve(seller)
                seller.full_clean()

    def test_small_seller_segment_cannot_be_changed_by_posting_to_another_route(self):
        seller = self.apply()
        response = self.client.post(reverse("small_food_seller_application"), self.payload(business_segment="food"))
        self.assertEqual(response.status_code, 200)
        seller.refresh_from_db()
        self.assertEqual(seller.business_segment, "shop")

    def test_new_small_seller_signup_routes_are_remembered(self):
        self.client.logout()
        for segment in ("food", "grocery"):
            self.client.get(reverse("signup"), {"seller": "small_" + segment})
            self.assertEqual(self.client.session["seller_signup_next"], "small_" + segment + "_seller_application")

    def test_mobile_small_food_and_grocery_forms(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.user)
        for segment in ("shop", "food", "grocery"):
            with self.subTest(segment=segment):
                user = User.objects.create_user("mobile-small-" + segment)
                client.force_authenticate(user)
                response = client.get("/api/v1/partners/applications/seller/", {"registration_type": "small", "business_segment": segment})
                self.assertEqual(response.status_code, 200)
                names = {field["name"] for field in response.data["fields"]}
                self.assertTrue({"pan_number", "gst_enrolment_number", "gstin"}.isdisjoint(names))
                form = self.small_form(self.payload(business_segment=segment), segment=segment)
                self.assertTrue(form.is_valid(), form.errors)
                response = client.post(
                    "/api/v1/partners/applications/seller/?registration_type=small&business_segment=" + segment,
                    self.payload(store_name="Mobile " + segment, business_segment=segment),
                    format="multipart",
                )
                self.assertEqual(response.status_code, 201, response.data)
                seller = SellerProfile.objects.get(user=user)
                self.assertEqual(seller.business_segment, segment)
                self.assertEqual(seller.registration_type, "small")
                self.assertEqual(seller.gstin, "")
                self.assertEqual(seller.pan_last4, "")
                self.assertEqual(seller.gst_enrolment_number, "")

    def test_small_forms_ignore_removed_fields_even_if_an_old_client_posts_them(self):
        for segment in ("shop", "food", "grocery"):
            with self.subTest(segment=segment):
                form = self.small_form(self.payload(business_segment=segment, pan_number="INVALIDPAN", gst_enrolment_number="INVALID"), segment=segment)
                self.assertTrue(form.is_valid(), form.errors)
                seller = form.save(commit=False)
                self.assertEqual(seller.pan_last4, "")
                self.assertEqual(seller.gst_enrolment_number, "")

    def test_registered_sellers_still_require_gstin_in_every_segment(self):
        for segment in ("shop", "food", "grocery"):
            with self.subTest(segment=segment):
                form = SellerApplicationForm(self.payload(business_segment=segment))
                self.assertFalse(form.is_valid())
                self.assertIn("gstin", form.errors)
                self.assertTrue(form.fields["gstin"].required)

    def test_small_seller_admin_hides_removed_fields_without_deleting_legacy_values(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from accounts.admin import SellerProfileAdmin
        seller = self.apply()
        seller.pan_last4 = "234F"
        seller.gst_enrolment_number = "ENROL12345678901"
        seller.save()
        form = self.small_form(self.payload(), instance=seller)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        seller.refresh_from_db()
        self.assertEqual(seller.pan_last4, "234F")
        self.assertEqual(seller.gst_enrolment_number, "ENROL12345678901")
        model_admin = SellerProfileAdmin(SellerProfile, AdminSite())
        request = RequestFactory().get("/")
        self.assertIn("pan_last4", model_admin.get_exclude(request, seller))
        self.assertIn("gst_enrolment_number", model_admin.get_exclude(request, seller))
        seller.registration_type = "registered"
        self.assertNotIn("pan_last4", model_admin.get_exclude(request, seller))

    def test_review_screen_requests_business_eligibility_without_pan_or_enrolment(self):
        seller = self.apply()
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("ops_seller_detail", args=[seller.pk]))
        self.assertContains(response, 'name="eligibility_checked"')
        self.assertNotContains(response, 'name="enrolment_checked"')
        self.assertNotContains(response, "PAN reference")
        self.assertNotContains(response, "Enrolment number")

    def test_no_gstin_field_and_privileged_fields_are_not_accepted(self):
        form = self.small_form(self.payload(status="approved", payouts_enabled=True, registration_type="registered", identity_status="verified"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("gstin", form.fields)
        self.assertNotIn("identity_status", form.fields)
        seller = form.save(commit=False)
        self.assertEqual(seller.registration_type, "small")
        self.assertEqual(seller.identity_status, "pending")
        self.assertFalse(seller.payouts_enabled)

    def test_application_retains_only_identity_and_bank_suffixes(self):
        seller = self.apply()
        self.assertEqual(seller.pan_last4, "")
        self.assertEqual(seller.gst_enrolment_number, "")
        self.assertEqual(seller.aadhaar_last4, "1234")
        self.assertEqual(seller.bank_account_last4, "9012")
        self.assertEqual(seller.gstin, "")
        self.assertEqual(seller.status, "pending")
        self.assertFalse(seller.is_approved)
        self.assertIsNotNone(seller.aadhaar_consent_at)
        self.assertNotIn("ABCDE1234F", str(seller.__dict__))
        self.assertNotIn("123456789012", str(seller.__dict__))
        self.assertEqual(self.client.get(reverse("seller_products")).status_code, 403)

    def test_full_aadhaar_no_consent_and_wrong_segment_are_rejected(self):
        for changes, field in (({"aadhaar_last4": "123456789012"}, "aadhaar_last4"), ({"aadhaar_consent": ""}, "aadhaar_consent"), ({"business_segment": "food"}, "business_segment"), ({"eligibility_declaration": ""}, "eligibility_declaration")):
            with self.subTest(field=field):
                form = self.small_form(self.payload(**changes))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_approval_and_payouts_require_identity_and_business_review(self):
        seller = self.apply()
        self.client.force_login(self.reviewer)
        self.client.post(reverse("update_seller_status", args=[seller.pk]), {"status": "approved"})
        seller.refresh_from_db()
        self.assertEqual(seller.status, "pending")
        self.client.post(reverse("verify_seller_payouts", args=[seller.pk]))
        seller.refresh_from_db()
        self.assertFalse(seller.payouts_enabled)
        seller.status = "approved"
        with self.assertRaises(ValidationError):
            seller.full_clean()

    def test_review_needs_real_checks_and_only_operations_staff_can_record_it(self):
        seller = self.apply()
        url = reverse("review_small_seller", args=[seller.pk])
        self.assertEqual(self.client.post(url, {"decision": "verified"}).status_code, 403)
        self.client.force_login(self.reviewer)
        self.client.post(url, {"decision": "verified", "reference": "REVIEW-001"})
        seller.refresh_from_db()
        self.assertEqual(seller.identity_status, "pending")
        self.verify(seller)
        self.assertEqual(seller.identity_status, "verified")
        self.assertEqual(seller.identity_verified_by, self.reviewer)
        self.assertEqual(seller.status, "pending")
        self.assertFalse(seller.payouts_enabled)

    def test_verified_seller_reuses_merchandise_workspace_and_product_form(self):
        seller = self.approve(self.apply())
        self.client.force_login(self.user)
        response = self.client.get(reverse("seller_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Small seller without GSTIN")
        self.assertNotIn("gst_rate", SellerProductForm(seller=seller).fields)
        self.assertNotContains(self.client.get(reverse("seller_add_product")), 'name="gst_rate"')

    def test_small_seller_price_keeps_platform_tax_and_removes_merchandise_gst(self):
        seller = self.approve(self.apply())
        product, variant = self.product(seller)
        self.assertEqual(product.effective_gst_rate, Decimal("0"))
        self.assertEqual(variant.customer_price_with_tax, Decimal("111.80"))
        with patch("delivery.coverage.has_local_coverage", return_value=True):
            pricing, quotes = build_parcel_pricing([{ "product": product, "variant": variant, "quantity": 1}], {"pincode": "243638", "latitude": "28.0731", "longitude": "78.7502"}, "cod")
        self.assertEqual(pricing["merchandise_gst"], Decimal("0.00"))
        self.assertEqual(pricing["platform_fee_gst"], Decimal("1.80"))
        self.assertEqual(pricing["customer_delivery_charge"], Decimal("30.00"))
        self.assertEqual(pricing["grand_total"], Decimal("141.80"))
        self.assertEqual(quotes[0]["provider"], "local")

    def test_small_seller_cannot_fall_back_to_courier_or_ship_outside_area(self):
        seller = self.approve(self.apply())
        product, variant = self.product(seller)
        rows = [{"product": product, "variant": variant, "quantity": 1}]
        with patch("payments.pricing.quote_delhivery") as courier:
            with self.assertRaises(DeliveryQuoteError):
                build_parcel_pricing(rows, {"pincode": "110001"}, "cod")
            with patch("delivery.coverage.has_local_coverage", return_value=False):
                with self.assertRaises(DeliveryQuoteError):
                    build_parcel_pricing(rows, {"pincode": "243638"}, "cod")
            courier.assert_not_called()

    def test_unverified_small_seller_cannot_publish_by_forging_status(self):
        seller = self.apply()
        seller.status = "approved"
        seller.save()
        self.product(seller)
        self.assertFalse(seller.is_approved)
        self.assertFalse(public_products().exists())

    def test_corrections_revoke_active_access_and_are_shown_to_the_seller(self):
        seller = self.approve(self.apply())
        self.client.post(reverse("review_small_seller", args=[seller.pk]), {"decision": "needs_changes", "note": "Please correct your business address."})
        seller.refresh_from_db()
        self.assertFalse(seller.is_approved)
        self.assertEqual(seller.status, "suspended")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("small_seller_application")), "Please correct your business address.")

    def test_withdrawing_consent_removes_aadhaar_reference_and_pauses_selling(self):
        seller = self.approve(self.apply())
        self.client.force_login(self.user)
        url = reverse("withdraw_small_seller_consent")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        seller.refresh_from_db()
        self.assertIsNone(seller.aadhaar_consent_at)
        self.assertEqual(seller.aadhaar_last4, "")
        self.assertFalse(seller.is_approved)
        self.assertFalse(seller.payouts_enabled)

    def test_reviewed_location_is_locked_and_registration_type_cannot_be_switched(self):
        seller = self.approve(self.apply())
        self.assertTrue(SellerProfileForm(instance=seller).fields["business_pincode"].disabled)
        self.client.force_login(self.user)
        response = self.client.get(reverse("registered_seller_application"))
        self.assertRedirects(response, reverse("small_seller_application"), fetch_redirect_response=False)

    def test_small_seller_settlement_has_no_gst_tcs(self):
        seller = self.approve(self.apply())
        product, variant = self.product(seller)
        order = Order.objects.create(user=self.user, full_name="Buyer", phone="9999999999", address="Market", city="Sahaswan", state="UP", pincode="243638", total_price="111.80", payment_method="online", payment_status="Paid", status="Processing")
        OrderItem.objects.create(order=order, product=product, variant=variant, quantity=1, price="111.80", seller_unit_price="100.00")
        settlement = create_settlements_for_order(order)[0]
        self.assertEqual(settlement.tcs_amount, Decimal("0.00"))
        self.assertEqual(settlement.net_amount, Decimal("100.00"))

    def test_local_customer_can_place_cod_order_with_small_seller_tax_snapshot(self):
        seller = self.approve(self.apply())
        product, variant = self.product(seller)
        buyer = User.objects.create_user("small-local-buyer")
        self.client.force_login(buyer)
        self.client.post(reverse("cart_add", args=[product.pk]), {"variant_id": variant.pk})
        data = {"full_name": "Local Buyer", "phone": "9999999999", "address": "Local market", "city": "Sahaswan", "state": "Uttar Pradesh", "pincode": "243638", "latitude": "28.073100", "longitude": "78.750200", "gps_accuracy_meters": "10", "gps_captured_at": timezone.now().isoformat(), "payment_method": "cod"}
        with patch("delivery.coverage.has_local_coverage", return_value=True):
            review = self.client.post(reverse("cod_checkout"), data)
            data["quote_token"] = review.context["quote_token"]
            response = self.client.post(reverse("cod_checkout"), data)
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user=buyer)
        self.assertEqual(order.total_price, Decimal("141.80"))
        self.assertEqual(order.items.get().product_tax_amount, Decimal("0.00"))
        self.assertEqual(order.items.get().platform_fee_tax_amount, Decimal("1.80"))
        self.assertEqual(order.sellerdeliverycharges.get().provider, "local")
        self.assertEqual(order.chargebreakdowns.get().customer_delivery_charge, Decimal("30.00"))

    def test_mobile_small_application_schema_and_submission_match_website(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.user)
        url = "/api/v1/partners/applications/seller/?registration_type=small"
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.data["fields"]}
        self.assertNotIn("gstin", names)
        self.assertNotIn("gst_enrolment_number", names)
        self.assertNotIn("pan_number", names)
        self.assertNotIn("identity_verified_by", names)
        response = client.post(url, self.payload(), format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        seller = SellerProfile.objects.get(user=self.user)
        self.assertEqual(seller.registration_type, "small")
        self.assertEqual(seller.identity_status, "pending")
        self.assertFalse(seller.payouts_enabled)

    def test_signup_remembers_only_known_seller_routes(self):
        self.client.logout()
        self.client.get(reverse("signup"), {"seller": "small"})
        self.assertEqual(self.client.session["seller_signup_next"], "small_seller_application")
        self.client.get(reverse("signup"), {"seller": "https://untrusted.example/"})
        self.assertNotEqual(self.client.session.get("seller_signup_next"), "https://untrusted.example/")

    def test_approved_small_seller_can_enable_payouts_after_bank_setup(self):
        seller = self.approve(self.apply())
        seller.razorpay_contact_id = "contact_test"
        seller.razorpay_fund_account_id = "fund_test"
        seller.save()
        self.client.post(reverse("verify_seller_payouts", args=[seller.pk]))
        seller.refresh_from_db()
        self.assertTrue(seller.payouts_enabled)

    def test_resubmission_invalidates_previous_review_and_payout_tokens(self):
        seller = self.verify(self.apply())
        seller.razorpay_fund_account_id = "fund_old"
        seller.save()
        self.client.force_login(self.user)
        self.client.post(reverse("small_seller_application"), self.payload())
        seller.refresh_from_db()
        self.assertEqual(seller.identity_status, "pending")
        self.assertIsNone(seller.identity_verified_by)
        self.assertEqual(seller.razorpay_fund_account_id, "")

    def test_aadhaar_consent_and_review_events_are_audited(self):
        from dashboard.models import AdminAuditLog
        seller = self.verify(self.apply())
        self.assertTrue(AdminAuditLog.objects.filter(action="seller.aadhaar_consent", entity_id=str(seller.pk), actor=self.user).exists())
        self.assertTrue(AdminAuditLog.objects.filter(action="seller.small_identity_review", entity_id=str(seller.pk), actor=self.reviewer).exists())

    def test_admin_cannot_enable_small_seller_payouts_before_verification(self):
        seller = self.apply()
        seller.payouts_enabled = True
        with self.assertRaises(ValidationError):
            seller.full_clean()

    def test_identity_upload_required_and_validated(self):
        data = self.payload()
        del data["aadhaar_image"]
        form = SmallSellerApplicationForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("aadhaar_image", form.errors)
        form = SmallSellerApplicationForm(data, {"aadhaar_image": SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")})
        self.assertFalse(form.is_valid())
        self.assertIn("aadhaar_image", form.errors)

    def test_identity_photo_is_private_and_removed_on_withdrawal(self):
        seller = self.apply()
        name = seller.aadhaar_image.name
        storage = seller.aadhaar_image.storage
        with self.assertRaises(ValueError):
            _ = seller.aadhaar_image.url
        url = reverse("seller_aadhaar_image", args=[seller.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.reviewer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        response.close()
        self.client.force_login(self.user)
        self.client.post(reverse("withdraw_small_seller_consent"))
        self.assertFalse(storage.exists(name))
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_review_requires_uploaded_photo(self):
        seller = self.apply()
        seller.aadhaar_image.delete()
        self.verify(seller)
        seller.refresh_from_db()
        self.assertEqual(seller.identity_status, "pending")

    def test_replacement_removes_previous_photo_and_resets_review(self):
        seller = self.verify(self.apply())
        previous = seller.aadhaar_image.name
        storage = seller.aadhaar_image.storage
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("small_seller_application"), self.payload())
        self.assertEqual(response.status_code, 302)
        seller.refresh_from_db()
        self.assertNotEqual(seller.aadhaar_image.name, previous)
        self.assertFalse(storage.exists(previous))
        self.assertTrue(storage.exists(seller.aadhaar_image.name))
        self.assertEqual(seller.identity_status, "pending")
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("ops_seller_detail", args=[seller.pk]))
        self.assertContains(response, reverse("seller_aadhaar_image", args=[seller.pk]))

    def test_oversized_identity_image_is_rejected(self):
        image = self.image()
        image.size = 8 * 1024 * 1024 + 1
        form = SmallSellerApplicationForm(self.payload(), {"aadhaar_image": image})
        self.assertFalse(form.is_valid())
        self.assertIn("aadhaar_image", form.errors)
