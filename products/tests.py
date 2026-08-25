from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import SellerProfile
from .models import Category, Product, ProductColor, ProductVariant, Wishlist


class MarketplacePricingTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("seller")
        self.seller = SellerProfile.objects.create(
            user=user, store_name="Test store", commission_percent=Decimal("10.00")
        )
        category = Category.objects.create(name="Test", slug="test")
        self.product = Product.objects.create(
            category=category, seller=self.seller, name="Item", price=Decimal("100.00")
        )
        color = ProductColor.objects.create(product=self.product, name="Black")
        self.variant = ProductVariant.objects.create(
            product=self.product, color=color, size="Standard", stock=1
        )

    def test_customer_product_price_includes_platform_fee(self):
        self.assertEqual(self.product.customer_price, Decimal("110.00"))

    def test_customer_variant_price_includes_platform_fee(self):
        self.assertEqual(self.variant.final_price, Decimal("110.00"))

    def test_marketplace_owned_product_has_no_seller_fee(self):
        self.product.seller = None
        self.assertEqual(self.product.customer_price, Decimal("100.00"))

    def test_long_product_names_generate_database_safe_unique_slugs(self):
        long_name = "Premium embroidered festive collection " + ("designer " * 28)

        first = Product.objects.create(
            category=self.product.category, name=long_name, price=Decimal("100.00")
        )
        second = Product.objects.create(
            category=self.product.category, name=long_name, price=Decimal("100.00")
        )

        self.assertLessEqual(len(first.slug), 255)
        self.assertLessEqual(len(second.slug), 255)
        self.assertNotEqual(first.slug, second.slug)

    @override_settings(PLATFORM_FEE_GST_PERCENT="18.00")
    def test_customer_tax_inclusive_price_matches_checkout_policy(self):
        self.assertEqual(self.product.customer_price_with_tax, Decimal("116.80"))
        self.assertEqual(self.variant.customer_price_with_tax, Decimal("116.80"))


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False)
class ProductStorefrontReadinessTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("approved-owner")
        self.seller = SellerProfile.objects.create(
            user=owner,
            store_name="Approved Store",
            status="approved",
            commission_percent=Decimal("10.00"),
        )
        self.category = Category.objects.create(name="Launch Test", slug="launch-test")
        self.product = Product.objects.create(
            category=self.category,
            seller=self.seller,
            name="Launch Shirt",
            slug="launch-shirt",
            description="A launch-ready product.",
            price=Decimal("100.00"),
            gst_rate=Decimal("5.00"),
            stock=0,
            moderation_status="approved",
        )
        color = ProductColor.objects.create(product=self.product, name="Black")
        self.variant = ProductVariant.objects.create(
            product=self.product, color=color, size="M", stock=2,
        )

    def _create_product(self, name, moderation_status="approved", legacy_stock=10, variant_stock=1):
        product = Product.objects.create(
            category=self.category,
            seller=self.seller,
            name=name,
            slug=name.lower().replace(" ", "-"),
            price=Decimal("50.00"),
            stock=legacy_stock,
            moderation_status=moderation_status,
        )
        if variant_stock is not None:
            color = ProductColor.objects.create(product=product, name="Blue")
            ProductVariant.objects.create(product=product, color=color, size="Standard", stock=variant_stock)
        return product

    def test_detail_is_accessible_with_tax_price_seo_and_accessible_controls(self):
        response = self.client.get(reverse("product_detail_page", args=[self.product.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹116.80")
        self.assertContains(response, "Inclusive of merchandise GST")
        self.assertContains(response, "images/product-placeholder.svg")
        self.assertContains(response, 'type="application/ld+json"')
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'aria-label="Select Black color"')

    def test_homepage_uses_only_sellable_products_and_renders_launch_ui(self):
        pending = self._create_product("Pending Home Item", moderation_status="pending")
        out_of_stock = self._create_product("Sold Out Home Item", variant_stock=0)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your city.")
        self.assertContains(response, "Choose how you shop")
        self.assertContains(response, "hero-ziyamart-v2.webp")
        self.assertContains(response, "storefront.css")
        self.assertContains(response, self.product.name)
        self.assertNotContains(response, pending.name)
        self.assertNotContains(response, out_of_stock.name)

    def test_pending_product_is_hidden_from_detail_list_api_and_related_products(self):
        pending = self._create_product("Pending Launch Item", moderation_status="pending")

        self.assertEqual(
            self.client.get(reverse("product_detail_page", args=[pending.slug])).status_code,
            404,
        )
        listing = self.client.get(reverse("product_list_page"))
        self.assertNotContains(listing, pending.name)
        detail = self.client.get(reverse("product_detail_page", args=[self.product.slug]))
        self.assertNotContains(detail, pending.name)
        self.assertEqual(
            self.client.get(reverse("api_product_detail", args=[pending.slug])).status_code,
            404,
        )

    def test_suspended_seller_product_is_not_public(self):
        self.seller.status = "suspended"
        self.seller.save(update_fields=["status"])

        self.assertEqual(
            self.client.get(reverse("product_detail_page", args=[self.product.slug])).status_code,
            404,
        )

    def test_public_stock_comes_from_active_variants_not_legacy_product_stock(self):
        phantom = self._create_product("Legacy Phantom", legacy_stock=99, variant_stock=None)

        response = self.client.get(reverse("product_list_page"))
        self.assertContains(response, self.product.name)
        self.assertNotContains(response, phantom.name)

    def test_wishlist_requires_post_and_only_accepts_public_product(self):
        customer = User.objects.create_user("wishlist-customer", password="test-password")
        self.client.login(username="wishlist-customer", password="test-password")

        url = reverse("toggle_wishlist", args=[self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(Wishlist.objects.filter(user=customer, product=self.product).exists())
