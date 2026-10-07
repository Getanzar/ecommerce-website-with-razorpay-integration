from django.urls import reverse
from rest_framework.test import APITestCase

from products.models import Category, Product, ProductColor, ProductVariant


class KidsAgeFilterTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Kids' Wear", slug="kids-wear")

    def product(self, age, gender="male", stock=1):
        product = Product.objects.create(
            category=self.category, name=f"Kids {age}",
            slug=f"kids-{age}-{gender}-{stock}", price="100",
            gender=gender, kids_age_group=age,
        )
        color = ProductColor.objects.create(product=product, name="Blue")
        ProductVariant.objects.create(product=product, color=color, size=age, stock=stock)
        return product.pk

    def matches(self, age):
        response = self.client.get(reverse("mobile-products"), {
            "category": "kids-wear", "gender": "male", "kids_age_group": age,
        })
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.data["results"]}

    def test_each_year_from_birth_through_fifteen_matches_only_its_band(self):
        products = {f"{age}-{age + 1}": self.product(f"{age}-{age + 1}") for age in range(15)}
        for age, product_id in products.items():
            with self.subTest(age=age):
                self.assertEqual(self.matches(age), {product_id})

    def test_legacy_ranges_match_both_years_without_crossing_boundaries(self):
        product_id = self.product("4-6")
        self.product("4-6", gender="female")
        self.product("4-6", stock=0)
        self.assertEqual(self.matches("4-5"), {product_id})
        self.assertEqual(self.matches("5-6"), {product_id})
        self.assertEqual(self.matches("3-4"), set())
        self.assertEqual(self.matches("6-7"), set())
        self.assertEqual(self.matches("4-6"), {product_id})

    def test_unknown_age_does_not_return_unfiltered_products(self):
        self.product("0-1")
        self.assertEqual(self.matches("invalid"), set())
