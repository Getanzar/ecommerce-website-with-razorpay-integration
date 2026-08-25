from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import SellerProfile
from products.models import Category, Product, ProductColor, ProductVariant


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False)
class SecureCartWorkflowTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("cart-seller")
        self.seller = SellerProfile.objects.create(
            user=owner,
            store_name="Cart Store",
            status="approved",
            commission_percent=Decimal("10.00"),
        )
        category = Category.objects.create(name="Cart Test", slug="cart-test")
        self.product = Product.objects.create(
            category=category,
            seller=self.seller,
            name="Cart Item",
            slug="cart-item",
            price=Decimal("100.00"),
            gst_rate=Decimal("5.00"),
            moderation_status="approved",
        )
        color = ProductColor.objects.create(product=self.product, name="Black")
        self.variant = ProductVariant.objects.create(
            product=self.product, color=color, size="M", stock=2,
        )

    def test_add_to_cart_requires_post_and_shows_tax_inclusive_total(self):
        url = reverse("cart_add", args=[self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

        response = self.client.post(url, {"variant_id": self.variant.pk})
        self.assertRedirects(response, reverse("cart_detail"))
        cart = self.client.get(reverse("cart_detail"))
        self.assertContains(cart, "₹116.80")
        self.assertContains(cart, "Includes ₹6.80 GST")

    def test_pending_product_cannot_be_added(self):
        self.product.moderation_status = "pending"
        self.product.save(update_fields=["moderation_status"])

        response = self.client.post(
            reverse("cart_add", args=[self.product.pk]),
            {"variant_id": self.variant.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.client.session.get("cart"))

    def test_suspended_seller_item_is_removed_from_existing_cart(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]),
            {"variant_id": self.variant.pk},
        )
        self.seller.status = "suspended"
        self.seller.save(update_fields=["status"])

        response = self.client.get(reverse("cart_detail"))
        self.assertContains(response, "Your cart is empty")
        self.assertEqual(self.client.session.get("cart"), {})

    def test_cart_mutation_endpoints_reject_get(self):
        for name in ("cart_remove", "cart_update", "decrease"):
            self.assertEqual(self.client.get(reverse(name, args=[self.variant.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("clear_cart")).status_code, 405)
