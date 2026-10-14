from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import SellerProfile
from .models import GroceryCategory, GroceryProduct, GroceryServiceArea, GroceryStore


@override_settings(SECURE_SSL_REDIRECT=False)
class GroceryCategoryBrowseTests(TestCase):
    def setUp(self):
        self.area = GroceryServiceArea.objects.create(pincode="243638")
        self.category = GroceryCategory.objects.create(name="Atta", slug="atta")
        self.stores = []
        for index in range(2):
            user = User.objects.create_user(f"category-seller-{index}")
            seller = SellerProfile.objects.create(user=user, store_name=f"Seller {index}", business_segment="grocery", status="approved", commission_percent=10)
            store = GroceryStore.objects.create(seller=seller, name=f"Kirana {index}", pincode="243638", estimated_delivery_minutes=30 + index * 15)
            store.service_areas.add(self.area)
            self.stores.append(store)
        self.product = GroceryProduct.objects.create(store=self.stores[0], category=self.category, name="Whole wheat atta", unit="1 kg", mrp=150, price=100, gst_rate=5, stock=10, image="groceries/products/atta.jpg")
        self.other = GroceryProduct.objects.create(store=self.stores[1], category=self.category, name="Premium atta", unit="1 kg", mrp=150, price=100, stock=10)

    def home(self):
        return self.client.get(reverse("grocery_home"), {"pincode": "243638"})

    def browse(self, **params):
        return self.client.get(reverse("grocery_category", args=[self.category.slug]), {"pincode": "243638", **params})

    def test_home_is_categories_with_product_collage_and_no_store_cards(self):
        response = self.home()
        self.assertContains(response, "Atta")
        self.assertContains(response, "groceries/products/atta.jpg")
        self.assertNotContains(response, "Kirana 0")
        self.assertEqual(response.context["grocery_categories"][0].available_count, 2)
        self.assertContains(response, reverse("grocery_category", args=["atta"]))

    def test_collage_has_at_most_four_in_stock_product_photos(self):
        for index in range(6):
            GroceryProduct.objects.create(store=self.stores[0], category=self.category, name=f"Atta {index}", unit="1 kg", mrp=100, price=80, stock=5, image=f"groceries/products/{index}.jpg")
        response = self.home()
        self.assertEqual(len(response.context["grocery_categories"][0].collage_products), 4)

    def test_category_shows_sellers_estimates_tax_inclusive_price_and_offer(self):
        response = self.browse()
        for text in ("Kirana 0", "Kirana 1", "30", "45", "₹20 delivery", "FREE on ₹200+", "₹116.80", "Save ₹33.20"):
            self.assertContains(response, text)
        self.assertNotContains(response, "seller-sponsored")

    def test_closed_unapproved_and_out_of_stock_products_are_hidden(self):
        self.product.stock = 0
        self.product.save()
        self.stores[1].accepts_orders = False
        self.stores[1].save()
        self.assertNotContains(self.home(), 'class="grocery-category-tile"')
        self.assertNotContains(self.browse(), "Premium atta")
        self.stores[1].accepts_orders = True
        self.stores[1].save()
        seller = self.stores[1].seller
        seller.status = "pending"
        seller.save()
        self.assertNotContains(self.browse(), "Premium atta")
        self.assertEqual(self.client.post(reverse("grocery_cart_add", args=[self.other.pk])).status_code, 404)

    def test_delivery_pincode_and_category_filter_and_search(self):
        other_category = GroceryCategory.objects.create(name="Soap", slug="soap")
        GroceryProduct.objects.create(store=self.stores[0], category=other_category, name="Bath soap", unit="1 bar", mrp=30, price=20, stock=10)
        self.assertNotContains(self.browse(), "Bath soap")
        self.assertNotContains(self.browse(q="Whole"), "Premium atta")
        self.stores[1].pincode = "110001"
        self.stores[1].save()
        self.assertNotContains(self.browse(), "Premium atta")
        response = self.client.get(reverse("grocery_category", args=["atta"]), {"pincode": "110001"})
        self.assertRedirects(response, reverse("grocery_home"))

    def test_add_stays_in_category_and_other_seller_cannot_replace_cart(self):
        self.home()
        response = self.client.post(reverse("grocery_cart_add", args=[self.product.pk]), {"category_slug": "atta"})
        self.assertRedirects(response, reverse("grocery_category", args=["atta"]) + "?pincode=243638")
        self.assertContains(self.browse(), "Complete or clear your cart")
        self.client.post(reverse("grocery_cart_add", args=[self.other.pk]), {"category_slug": "atta"})
        self.assertEqual(self.client.session["grocery_cart"]["store_id"], self.stores[0].pk)
        self.assertNotIn(str(self.other.pk), self.client.session["grocery_cart"]["items"])

    def test_category_without_photos_uses_fallback(self):
        self.product.image = ""
        self.product.save()
        self.assertContains(self.home(), "images/product-placeholder.svg")

    def test_search_paginates_and_retains_category(self):
        for index in range(25):
            GroceryProduct.objects.create(store=self.stores[0], category=self.category, name=f"Atta {index}", unit="1 kg", mrp=100, price=80, stock=5)
        response = self.browse(page="2")
        self.assertEqual(response.context["page"].number, 2)
        self.assertContains(response, "Previous")
