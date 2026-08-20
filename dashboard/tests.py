import base64
from unittest.mock import Mock, patch
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from accounts.models import SellerProfile
from products.models import CatalogRequest, Category, Product, SubCategory
from orders.models import Order, OrderItem
from orders.settlements import create_settlements_for_order

from dashboard.ai_services import enhance_product_image, generate_listing_copy
from dashboard.views import _parse_seller_variants


@override_settings(
    CLOUDFLARE_ACCOUNT_ID="test-account",
    CLOUDFLARE_API_TOKEN="test-token",
    CLOUDFLARE_TEXT_MODEL="@cf/test/text",
    CLOUDFLARE_IMAGE_MODEL="@cf/test/image",
)
class CloudflareAIServiceTests(SimpleTestCase):
    @patch("dashboard.ai_services.requests.post")
    def test_listing_copy_uses_cloudflare_workers_ai(self, post):
        response = Mock(ok=True)
        response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"name":"Navy Cotton Shirt","description":"A navy cotton shirt."}'
            },
        }
        post.return_value = response

        result = generate_listing_copy("Navy cotton shirt with regular fit", "Shirts", "Navy")

        self.assertEqual(result["name"], "Navy Cotton Shirt")
        self.assertIn("/accounts/test-account/ai/run/@cf/test/text", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    @patch("dashboard.ai_services.requests.post")
    def test_image_edit_accepts_cloudflare_base64_response(self, post):
        encoded = base64.b64encode(b"generated-image").decode("ascii")
        response = Mock(ok=True, headers={"Content-Type": "application/json"})
        response.json.return_value = {"success": True, "result": {"image": encoded}}
        post.return_value = response
        image = SimpleUploadedFile("product.png", b"original", content_type="image/png")

        result = enhance_product_image(image)

        self.assertEqual(result, encoded)
        self.assertIn("/accounts/test-account/ai/run/@cf/test/image", post.call_args.args[0])
        self.assertIn("input_image_0", post.call_args.kwargs["files"])

    @patch("dashboard.ai_services.requests.post")
    def test_listing_parser_ignores_other_json_objects(self, post):
        response = Mock(ok=True)
        response.json.return_value = {
            "result": {
                "response": 'Example {"invalid": true}\nFinal: {"name":"Shirt","description":"A shirt."}'
            }
        }
        post.return_value = response

        result = generate_listing_copy("A plain shirt with a regular fit", "Shirts", "Blue")

        self.assertEqual(result, {"name": "Shirt", "description": "A shirt."})


@override_settings(ROOT_URLCONF="dashboard.urls")
class SellerCatalogModerationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "password")
        seller_user = User.objects.create_user("seller")
        self.seller = SellerProfile.objects.create(
            user=seller_user, store_name="Seller store", status="approved"
        )
        self.category = Category.objects.create(name="Clothing", slug="clothing")
        self.client.force_login(self.admin)

    def test_admin_approval_is_the_only_action_that_publishes_seller_product(self):
        product = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Seller shirt",
            price=Decimal("100.00"),
            stock=5,
            is_active=False,
            moderation_status=Product.MODERATION_PENDING,
        )

        response = self.client.post(
            f"/products/{product.id}/review/", {"action": "approve"}
        )
        product.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(product.moderation_status, Product.MODERATION_APPROVED)
        self.assertTrue(product.is_active)
        self.assertEqual(product.reviewed_by, self.admin)

    def test_approved_category_request_creates_customer_catalog_category(self):
        catalog_request = CatalogRequest.objects.create(
            seller=self.seller,
            request_type=CatalogRequest.TYPE_CATEGORY,
            name="Handmade",
        )

        response = self.client.post(
            f"/catalog-requests/{catalog_request.id}/review/", {"action": "approve"}
        )
        catalog_request.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(catalog_request.status, CatalogRequest.STATUS_APPROVED)
        self.assertTrue(Category.objects.filter(name="Handmade").exists())


class SellerMarketplaceMoneyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer")
        seller_user = User.objects.create_user("money-seller")
        self.seller = SellerProfile.objects.create(
            user=seller_user, store_name="Money seller", status="approved",
            commission_percent=Decimal("10.00"),
        )
        self.category = Category.objects.create(name="Money clothing", slug="money-clothing")
        self.product = Product.objects.create(
            seller=self.seller, category=self.category, name="Jacket",
            price=Decimal("1000.00"), stock=2,
        )

    def test_customer_fee_is_added_while_seller_receives_entered_price(self):
        self.assertEqual(self.product.customer_price, Decimal("1100.00"))
        order = Order.objects.create(
            user=self.user, full_name="Buyer", phone="9999999999", address="Road",
            city="City", state="State", pincode="123456", total_price=Decimal("1100.00"),
            status="Processing", payment_method="online", payment_status="Paid",
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            quantity=1, price=Decimal("1100.00"),
        )
        settlement = create_settlements_for_order(order)[0]
        self.assertEqual(settlement.net_amount, Decimal("1000.00"))
        self.assertEqual(settlement.commission_amount, Decimal("100.00"))


class SellerVariantCreationTests(TestCase):
    def test_manual_sizes_for_each_color_are_parsed(self):
        variants = [
            {
                "name": "Navy",
                "hex_code": "#000080",
                "variants": [
                    {"size": "S", "stock": "3", "sku": "NAV-S", "price": ""},
                    {"size": "Custom 42", "stock": "4", "sku": "NAV-42", "price": "120"},
                ],
            },
            {
                "name": "Red",
                "hex_code": "#FF0000",
                "variants": [{"size": "M", "stock": "2", "sku": "RED-M", "price": ""}],
            },
        ]
        request = RequestFactory().post(
            "/seller/products/add/", {"variants_json": json.dumps(variants)}
        )
        parsed = _parse_seller_variants(request)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["variants"][1]["size"], "Custom 42")
        self.assertEqual(parsed[0]["variants"][1]["stock"], 4)
        self.assertEqual(parsed[0]["variants"][1]["price"], Decimal("120"))


@override_settings(ROOT_URLCONF="dashboard.urls")
class SellerCatalogDuplicateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("catalog-seller")
        self.seller = SellerProfile.objects.create(
            user=self.user, store_name="Catalog store", status="approved"
        )
        self.category = Category.objects.create(name="Kids Wear", slug="kids-wear")
        self.client.force_login(self.user)

    def _messages(self, response):
        return " ".join(str(message) for message in get_messages(response.wsgi_request))

    def test_similar_existing_category_is_not_requested_twice(self):
        response = self.client.post(
            "/seller/catalog-requests/",
            {"request_type": "category", "name": "  KIDS--wear  "},
        )

        self.assertFalse(CatalogRequest.objects.exists())
        self.assertIn("already exists", self._messages(response))

    def test_similar_existing_subcategory_under_same_parent_is_not_requested(self):
        SubCategory.objects.create(category=self.category, name="T Shirts")
        response = self.client.post(
            "/seller/catalog-requests/",
            {
                "request_type": "subcategory",
                "parent_category": self.category.pk,
                "name": "t-shirts",
            },
        )

        self.assertFalse(CatalogRequest.objects.exists())
        self.assertIn("already exists", self._messages(response))

    def test_legacy_pending_request_does_not_require_new_approval(self):
        other_user = User.objects.create_user("other-seller")
        other_seller = SellerProfile.objects.create(
            user=other_user, store_name="Other store", status="approved"
        )
        CatalogRequest.objects.create(
            seller=other_seller,
            request_type=CatalogRequest.TYPE_SUBCATEGORY,
            parent_category=self.category,
            name="Party Dresses",
        )

        response = self.client.post(
            "/seller/catalog-requests/",
            {
                "request_type": "subcategory",
                "parent_category": self.category.pk,
                "name": "party-dresses",
            },
        )

        self.assertEqual(CatalogRequest.objects.count(), 1)
        self.assertTrue(
            SubCategory.objects.filter(
                category=self.category, name="party-dresses"
            ).exists()
        )
        self.assertIn("ready to use", self._messages(response))

    def test_new_category_is_available_immediately(self):
        response = self.client.post(
            "/seller/catalog-requests/",
            {"request_type": "category", "name": "Ethnic Wear"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["created"])
        self.assertTrue(Category.objects.filter(pk=result["id"]).exists())
        self.assertFalse(CatalogRequest.objects.exists())
