from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import SellerProfile
from .models import Category, Product, ProductColor, ProductVariant


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
