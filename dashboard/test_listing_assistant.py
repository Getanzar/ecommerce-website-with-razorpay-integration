import io
import base64
import json
from unittest.mock import Mock, patch

from PIL import Image
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.core.management import call_command, CommandError
from django.template.loader import render_to_string
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import SellerProfile
from dashboard.listing_assistant import ListingAssistantError, generate_draft, listing_choices, photo_content, validate_draft
from dashboard.models import SellerListingAIUsage
from products.models import Category, Product


def photo():
    stream = io.BytesIO()
    Image.new("RGB", (12, 12), "blue").save(stream, "PNG")
    return SimpleUploadedFile("shirt.png", stream.getvalue(), content_type="image/png")


def draft(category=None):
    return {"name": "Blue shirt", "description": "A blue shirt with a button front.", "brand": "", "unit": "",
            "category_id": category, "colours": ["Blue"], "keywords": ["shirt"], "review_notes": ["Confirm fabric and sizes."]}


def provider(value=None):
    response = Mock(ok=True)
    response.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value or draft())}]}}]}
    return response


@override_settings(GEMINI_API_KEY="test-key-not-real", SELLER_LISTING_AI_MODEL="gemini-3.1-flash-lite", SELLER_LISTING_AI_DAILY_LIMIT=2)
class ListingAssistantTests(TestCase):
    @patch("dashboard.listing_assistant.requests.post")
    def test_catalogue_photo_is_validated_and_shared_by_web_and_mobile(self, post):
        image_response = Mock(ok=True)
        image_response.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(photo().read()).decode("ascii")}}
        ]}}]}
        for client, url in ((self.client, self.web_url), (self.api, self.api_url)):
            post.side_effect = [provider(), image_response]
            response = client.post(url, {"kind": "shop", "photos": photo(), "enhance_photo": "true"})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["catalogue_image"]["mime_type"], "image/jpeg")
            with Image.open(io.BytesIO(base64.b64decode(result["catalogue_image"]["data"]))) as generated:
                self.assertEqual(generated.format, "JPEG")
            self.assertTrue(result["review_required"])
        self.assertEqual(Product.objects.count(), 0)

    @patch("dashboard.listing_assistant.requests.post")
    def test_invalid_provider_image_is_never_returned_as_a_photo(self, post):
        image_response = Mock(ok=True)
        image_response.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b"invalid pixels").decode("ascii")}}
        ]}}]}
        post.side_effect = [provider(), image_response]
        response = self.client.post(self.web_url, {"kind": "shop", "photos": photo(), "enhance_photo": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("catalogue_image", response.json())
        self.assertIn("image_warning", response.json())

    @patch("dashboard.listing_assistant.requests.post")
    def test_image_failure_keeps_text_and_does_not_charge_an_extra_attempt(self, post):
        post.side_effect = [provider(), Mock(ok=False, status_code=429)]
        response = self.client.post(self.web_url, {"kind": "shop", "photos": photo(), "enhance_photo": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("image_warning", response.json())
        self.assertNotIn("catalogue_image", response.json())
        self.assertEqual(response.json()["fields"]["name"], "Blue shirt")
        self.assertEqual(SellerListingAIUsage.objects.get().attempts, 1)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("listing-seller", password="testpass")
        self.seller = SellerProfile.objects.create(user=self.user, store_name="Test store", status="approved", business_segment="shop")
        self.category = Category.objects.create(name="Clothes", slug="clothes")
        self.client.force_login(self.user)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION="Token " + Token.objects.create(user=self.user).key)
        self.web_url = reverse("seller_listing_draft")
        self.api_url = "/api/v1/partners/seller/listing-assistant/"

    @patch("dashboard.listing_assistant.requests.post")
    def test_web_and_mobile_share_usage_and_never_create_products(self, post):
        post.return_value = provider(draft(self.category.pk))
        web = self.client.post(self.web_url, {"kind": "shop", "photos": photo()})
        self.assertEqual(web.status_code, 200, web.content)
        self.assertTrue(web.json()["review_required"])
        self.assertEqual(web.json()["fields"]["category"], str(self.category.pk))
        self.assertEqual(web.json()["suggested_category"], "Clothes")
        native = self.api.post(self.api_url, {"kind": "shop", "photos": photo()}, format="multipart")
        self.assertEqual(native.status_code, 200, native.content)
        self.assertEqual(native.json()["remaining_today"], 0)
        denied = self.client.post(self.web_url, {"kind": "shop", "photos": photo()})
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(SellerListingAIUsage.objects.get().attempts, 2)

    @patch("dashboard.listing_assistant.requests.post")
    def test_each_seller_type_can_generate_without_paid_plan(self, post):
        post.return_value = provider()
        for kind in ("shop", "food", "grocery"):
            self.seller.business_segment = kind
            self.seller.save(update_fields=["business_segment"])
            SellerListingAIUsage.objects.all().delete()
            response = self.api.post(self.api_url, {"kind": kind, "photos": photo()}, format="multipart")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertFalse(self.seller.ai_subscription_active)
            self.assertNotIn("price", response.json()["fields"])
            self.assertNotIn("stock", response.json()["fields"])

    @patch("dashboard.listing_assistant.requests.post")
    def test_unapproved_and_wrong_segment_do_not_call_provider(self, post):
        for data in ({"kind": "food"}, {"kind": "anything"}):
            response = self.client.post(self.web_url, {**data, "photos": photo()})
            self.assertEqual(response.status_code, 403)
        self.seller.status = "pending"
        self.seller.save(update_fields=["status"])
        self.assertEqual(self.api.post(self.api_url, {"kind": "shop", "photos": photo()}, format="multipart").status_code, 403)
        post.assert_not_called()
        self.assertFalse(SellerListingAIUsage.objects.exists())

    @patch("dashboard.listing_assistant.requests.post")
    def test_invalid_inputs_do_not_consume_usage(self, post):
        cases = [
            {"kind": "shop"},
            {"kind": "shop", "photos": [photo(), photo(), photo(), photo()]},
            {"kind": "shop", "photos": SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")},
            {"kind": "shop", "photos": photo(), "notes": "x" * 2001},
        ]
        for data in cases:
            self.assertEqual(self.client.post(self.web_url, data).status_code, 400)
        post.assert_not_called()
        self.assertFalse(SellerListingAIUsage.objects.exists())

    @override_settings(GEMINI_API_KEY="")
    @patch("dashboard.listing_assistant.requests.post")
    def test_unconfigured_provider_is_explicit_and_does_not_charge_usage(self, post):
        response = self.client.post(self.web_url, {"kind": "shop", "photos": photo()})
        self.assertEqual(response.status_code, 503)
        self.assertIn("manually", response.json()["error"])
        self.assertFalse(SellerListingAIUsage.objects.exists())
        post.assert_not_called()

    @patch("dashboard.listing_assistant.requests.post")
    def test_provider_payload_uses_gemini_header_inline_images_and_json_schema(self, post):
        post.return_value = provider()
        generate_draft(self.seller, "shop", "Cotton shirt", [photo(), photo()])
        self.assertEqual(post.call_count, 1)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(post.call_args.args[0], "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key-not-real")
        self.assertNotIn("test-key-not-real", post.call_args.args[0])
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertFalse(payload["generationConfig"]["responseJsonSchema"]["additionalProperties"])
        images = [row for row in payload["contents"][0]["parts"] if "inlineData" in row]
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]["inlineData"]["mimeType"], "image/jpeg")
        self.assertNotIn("store", payload)
        self.assertNotIn(self.user.email, json.dumps(payload)) if self.user.email else None

    @patch("dashboard.listing_assistant.requests.post")
    def test_provider_errors_are_safe_and_failed_attempts_are_bounded(self, post):
        post.return_value = Mock(ok=False, status_code=500, text="private provider diagnostic")
        response = self.client.post(self.web_url, {"kind": "shop", "photos": photo()})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.json()["error"])
        self.assertEqual(SellerListingAIUsage.objects.get().attempts, 1)

    @patch("dashboard.listing_assistant.requests.post")
    def test_refused_or_truncated_output_is_never_applied(self, post):
        for payload in ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, {"promptFeedback": {"blockReason": "SAFETY"}}):
            post.return_value = Mock(ok=True)
            post.return_value.json.return_value = payload
            response = self.client.post(self.web_url, {"kind": "shop", "photos": photo()})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("fields", response.json())

    def test_result_validation_rejects_extra_fields_and_wrong_types(self):
        for value in ({**draft(), "price": "10"}, {**draft(), "name": []}, {**draft(), "keywords": [42]}, {**draft(), "unit": "x" * 41}):
            with self.assertRaises(ValueError):
                validate_draft(value, [], "shop")
        value = validate_draft(draft(99999), [], "shop")
        self.assertIsNone(value["draft"]["category_id"])
        self.assertNotIn("category", value["fields"])

    def test_grocery_and_menu_fields_are_limited_to_supported_suggestions(self):
        grocery = validate_draft({**draft(self.category.pk), "brand": "Test brand", "unit": "500 g"}, [{"id": self.category.pk, "name": "Staples"}], "grocery")
        self.assertEqual(set(grocery["fields"]), {"name", "description", "brand", "unit", "category"})
        menu = validate_draft(draft(1), [{"id": 1, "name": "Lunch"}], "food")
        self.assertEqual(menu["fields"]["section_name"], "Lunch")
        self.assertNotIn("food_type", menu["fields"])

    def test_food_categories_are_scoped_to_sellers_restaurant(self):
        from food.models import Restaurant, MenuSection
        own = Restaurant.objects.create(seller=self.seller, name="Own kitchen", slug="own-kitchen")
        section = MenuSection.objects.create(restaurant=own, name="Lunch")
        other_user = User.objects.create_user("other-seller")
        other_seller = SellerProfile.objects.create(user=other_user, store_name="Other", status="approved", business_segment="food")
        other = Restaurant.objects.create(seller=other_seller, name="Other", slug="other")
        MenuSection.objects.create(restaurant=other, name="Private menu")
        self.assertEqual(listing_choices(self.seller, "food"), [{"id": section.pk, "name": "Lunch"}])

    def test_anonymous_access_and_web_csrf_are_enforced(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.web_url).status_code, 302)
        self.assertIn(APIClient().post(self.api_url).status_code, (401, 403))
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(secure.post(self.web_url, {"kind": "shop", "photos": photo()}).status_code, 403)

    def test_legacy_paid_ai_routes_are_removed(self):
        for action in ("copy", "image", "buy", "confirm"):
            self.assertEqual(self.client.post(f"/dashboard/seller/ai/{action}/").status_code, 404)

    def test_all_three_web_forms_render_new_assistant(self):
        from dashboard.forms import SellerProductForm
        from groceries.forms import GroceryProductForm
        from food.forms import MenuItemForm
        cases = [
            ("dashboard/seller/add_product.html", SellerProductForm(seller=self.seller), "shop"),
            ("groceries/seller/product_form.html", GroceryProductForm(), "grocery"),
            ("food/seller/menu_item_form.html", MenuItemForm(), "food"),
        ]
        for template, form, kind in cases:
            rendered = render_to_string(template, {"seller": self.seller, "form": form})
            self.assertIn(f'data-kind="{kind}"', rendered)
            self.assertNotIn("buy-ai-plan", rendered)
            self.assertNotIn("enhance-images", rendered)
            self.assertIn("Apply draft to form", rendered)

    def test_photo_validation_restores_stream_and_checks_real_pixels(self):
        upload = photo()
        self.assertEqual(photo_content(upload)["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(upload.tell(), 0)
        upload.size = 9 * 1024 * 1024
        with self.assertRaises(ListingAssistantError):
            photo_content(upload)

    @patch("dashboard.listing_assistant.requests.post")
    def test_gemini_thought_parts_are_not_treated_as_listing_json(self, post):
        result = provider()
        result.json.return_value["candidates"][0]["content"]["parts"].insert(0, {"thought": True, "text": "Internal reasoning"})
        post.return_value = result
        self.assertEqual(generate_draft(self.seller, "shop", "", [photo()])["draft"]["name"], "Blue shirt")

    @patch("dashboard.listing_assistant.requests.post")
    def test_gemini_quota_error_keeps_draft_fields_out_of_response(self, post):
        post.return_value = Mock(ok=False, status_code=429)
        response = self.api.post(self.api_url, {"kind": "shop", "photos": photo()}, format="multipart")
        self.assertEqual(response.status_code, 503)
        self.assertIn("quota", response.json()["error"])
        self.assertNotIn("fields", response.json())

    @override_settings(SELLER_LISTING_AI_MODEL="gpt-4.1-mini")
    @patch("dashboard.listing_assistant.requests.post")
    def test_stale_openai_model_configuration_does_not_send_key_or_spend_quota(self, post):
        with self.assertRaises(ListingAssistantError):
            generate_draft(self.seller, "shop", "", [photo()])
        post.assert_not_called()
        self.assertFalse(SellerListingAIUsage.objects.exists())

    @patch("dashboard.management.commands.check_listing_assistant.requests.get")
    def test_configuration_check_hides_key_and_does_not_generate(self, get):
        get.return_value = Mock(ok=True)
        get.return_value.json.return_value = {"supportedGenerationMethods": ["generateContent"]}
        output = io.StringIO()
        call_command("check_listing_assistant", verify_provider=True, stdout=output)
        self.assertIn("access verified", output.getvalue())
        self.assertNotIn("test-key-not-real", output.getvalue())
        self.assertEqual(get.call_args.kwargs["headers"]["x-goog-api-key"], "test-key-not-real")
        self.assertNotIn("test-key-not-real", get.call_args.args[0])
        self.assertFalse(SellerListingAIUsage.objects.exists())

    @patch("dashboard.management.commands.check_listing_assistant.requests.get")
    def test_configuration_check_is_offline_unless_requested(self, get):
        call_command("check_listing_assistant", stdout=io.StringIO())
        get.assert_not_called()

    @patch("dashboard.management.commands.check_listing_assistant.requests.get")
    def test_configuration_check_reports_model_access_failure_without_secret(self, get):
        get.return_value = Mock(ok=False, status_code=403)
        with self.assertRaisesMessage(CommandError, "HTTP 403"):
            call_command("check_listing_assistant", verify_provider=True, stdout=io.StringIO())
