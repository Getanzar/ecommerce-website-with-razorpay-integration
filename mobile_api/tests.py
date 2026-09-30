from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from django.test import override_settings

from accounts.models import EmailOTP, SellerProfile, UserProfile
from addresses.models import Address
from cart.models import Cart, CartItem
from products.models import Category, Product, ProductColor, ProductVariant
from food.models import FoodServiceArea, MenuItem, MenuItemOption, MenuSection, Restaurant
from groceries.models import GroceryCategory, GroceryProduct, GroceryServiceArea, GroceryStore
from orders.models import Order


class AuthenticationApiTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @patch("mobile_api.views.send_email_otp", return_value=True)
    def test_signup_creates_inactive_user(self, _send):
        response = self.client.post(reverse("mobile-signup"), {"username":"newbuyer", "email":"buyer@example.com", "phone":"9876543210", "password":"strongpass123"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(User.objects.get(username="newbuyer").is_active)

    def test_login_and_profile_require_token(self):
        user = User.objects.create_user("buyer", email="buyer@example.com", password="strongpass123")
        UserProfile.objects.get_or_create(user=user)
        response = self.client.post(reverse("mobile-login"), {"identity":"buyer@example.com", "password":"strongpass123"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get(reverse("mobile-profile")).status_code, 200)

    def test_verify_otp_activates_account(self):
        user = User.objects.create_user("waiting", email="wait@example.com", password="strongpass123", is_active=False)
        UserProfile.objects.get_or_create(user=user)
        from django.utils import timezone
        from datetime import timedelta
        EmailOTP.objects.create(user=user, otp="123456", expires_at=timezone.now()+timedelta(minutes=5))
        response = self.client.post(reverse("mobile-verify-otp"), {"email":"wait@example.com", "otp":"123456"}, format="json")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db(); self.assertTrue(user.is_active)

    @patch("mobile_api.views.send_password_reset_otp", return_value=True)
    def test_password_reset_request_does_not_reveal_account_existence(self, _send):
        user = User.objects.create_user("resetbuyer", email="reset@example.com", password="old-password-123")
        known = self.client.post(reverse("mobile-password-reset-request"), {"email":user.email}, format="json")
        unknown = self.client.post(reverse("mobile-password-reset-request"), {"email":"missing@example.com"}, format="json")
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)

    def test_password_reset_changes_password_and_invalidates_tokens(self):
        user = User.objects.create_user("resetbuyer", email="reset@example.com", password="old-password-123")
        token = Token.objects.create(user=user)
        from django.utils import timezone
        from datetime import timedelta
        EmailOTP.objects.create(user=user, otp="123456", expires_at=timezone.now()+timedelta(minutes=5))
        response = self.client.post(reverse("mobile-password-reset-confirm"), {"email":user.email, "otp":"123456", "password":"new-strong-password-456"}, format="json")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("new-strong-password-456"))
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_account_preferences_push_device_and_deletion_request(self):
        user = User.objects.create_user("settingsbuyer", password="strongpass123")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        preferences = self.client.patch(reverse("mobile-notification-preferences"), {"order_updates":True, "payment_updates":False, "promotions":True}, format="json")
        self.assertEqual(preferences.status_code, 200)
        self.assertFalse(preferences.data["payment_updates"])
        device = self.client.post(reverse("mobile-push-device"), {"expo_push_token":"ExponentPushToken[test-device]", "platform":"android"}, format="json")
        self.assertEqual(device.status_code, 201)
        deletion = self.client.post(reverse("mobile-account-delete-request"), {"reason":"No longer needed"}, format="json")
        self.assertEqual(deletion.status_code, 201)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())


class CommerceApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", password="strongpass123")
        UserProfile.objects.get_or_create(user=self.user)
        self.client.force_authenticate(self.user)
        category = Category.objects.create(name="Shoes", slug="shoes")
        product = Product.objects.create(category=category, name="Running Shoe", slug="running-shoe", price="1000", stock=5)
        color = ProductColor.objects.create(product=product, name="Black", hex_code="#000000")
        self.variant = ProductVariant.objects.create(product=product, color=color, size="9", stock=5)

    def test_catalog_returns_variants(self):
        ProductVariant.objects.create(product=self.variant.product, color=self.variant.color, size="10", stock=0)
        response = self.client.get(reverse("mobile-product-detail", kwargs={"slug":"running-shoe"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["variants"][0]["size"], "9")
        self.assertEqual(len(response.data["variants"]), 2)
        self.assertIn("specifications", response.data)

    def test_catalog_pages_have_stable_order_and_bounded_size(self):
        for index in range(55):
            product = Product.objects.create(category=self.variant.product.category, name=f"Paged Shoe {index}", slug=f"paged-{index}", price="100")
            color = ProductColor.objects.create(product=product, name="Black")
            ProductVariant.objects.create(product=product, color=color, size="M", stock=1)
        first = self.client.get(reverse("mobile-products"), {"q": "Paged Shoe", "sort": "price_low"})
        second = self.client.get(reverse("mobile-products"), {"q": "Paged Shoe", "sort": "price_low", "page": 2})
        self.assertEqual(first.data["count"], 55)
        self.assertEqual(len(first.data["results"]), 24)
        self.assertTrue(first.data["next"])
        self.assertFalse({r["id"] for r in first.data["results"]} & {r["id"] for r in second.data["results"]})
        capped = self.client.get(reverse("mobile-products"), {"page_size": 999})
        self.assertEqual(len(capped.data["results"]), 50)

    def test_catalog_search_and_sort_options_are_safe(self):
        for sort in ("newest", "price_low", "price_high", "rating", "popularity"):
            response = self.client.get(reverse("mobile-products"), {"q": "Running", "sort": sort})
            self.assertEqual(response.status_code, 200)

    def test_product_catalog_uses_bounded_pagination(self):
        response = self.client.get(reverse("mobile-products"))

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, dict)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertLessEqual(len(response.data["results"]), 24)

    def test_grocery_catalog_uses_bounded_pagination(self):
        response = self.client.get(reverse("mobile-grocery-products"))

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, dict)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertLessEqual(len(response.data["results"]), 24)

    def test_authenticated_cart_add_and_update(self):
        added = self.client.post(reverse("mobile-cart-add"), {"variant_id":self.variant.id, "quantity":2}, format="json")
        self.assertEqual(added.status_code, 201)
        cart = self.client.get(reverse("mobile-cart"))
        self.assertEqual(cart.data["item_count"], 2)

    def test_invalid_cart_quantities_do_not_write(self):
        for value in ("many", None, True, 1.5, -1, 0, 11, "9" * 100):
            response = self.client.post(reverse("mobile-cart-add"), {"variant_id": self.variant.pk, "quantity": value}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(CartItem.objects.exists())

    def test_invalid_product_filters_return_400(self):
        for params in ({"min_price": "NaN"}, {"max_price": "Infinity"}, {"min_price": "-1"}, {"rating": "6"}, {"rating": "bad"}, {"min_price": "20", "max_price": "10"}, {"seller": "9" * 100}):
            response = self.client.get(reverse("mobile-products"), params)
            self.assertEqual(response.status_code, 400, response.data)
        for params in ({"seller": "Named seller"}, {"subcategory": "Named category"}):
            self.assertEqual(self.client.get(reverse("mobile-products"), params).status_code, 200)

    def test_invalid_cart_ids_return_400(self):
        for route, field in (("mobile-cart-add", "variant_id"), ("mobile-food-cart-add", "option_id"), ("mobile-grocery-cart-add", "product_id")):
            for value in ("bad", True, [], "9" * 100):
                response = self.client.post(reverse(route), {field: value}, format="json")
                self.assertEqual(response.status_code, 400, response.data)

    def test_cart_add_consolidates_legacy_duplicate_variant_rows(self):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.variant.product, variant=self.variant, quantity=1)
        CartItem.objects.create(cart=cart, product=self.variant.product, variant=self.variant, quantity=1)
        response = self.client.post(reverse("mobile-cart-add"), {"variant_id":self.variant.id}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.filter(cart=cart, variant=self.variant).count(), 1)
        self.assertEqual(response.data["quantity"], 3)

    def test_address_is_owned_and_first_is_default(self):
        response = self.client.post(reverse("mobile-addresses"), {"full_name":"Test Buyer", "phone":"9876543210", "address_line_1":"1 Main Road", "address_line_2":"", "city":"Sahaswan", "state":"Uttar Pradesh", "pincode":"243638", "address_type":"Home"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Address.objects.get(pk=response.data["id"]).is_default)

    def test_shop_quote_hides_internal_fees_and_checkout_is_idempotent(self):
        address = Address.objects.create(
            user=self.user,
            full_name="Test Buyer",
            phone="9876543210",
            address_line_1="1 Main Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            address_type="Home",
            is_default=True,
        )
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=self.variant.product,
            variant=self.variant,
            quantity=1,
        )
        quoted = self.client.post(
            reverse("mobile-checkout-quote", kwargs={"kind": "shop"}),
            {"address_id": address.id},
            format="json",
        )
        self.assertEqual(quoted.status_code, 201)
        self.assertNotIn("platform_fee", quoted.data["price"])
        self.assertNotIn("platform_fee_gst", quoted.data["price"])
        self.assertIn("total", quoted.data["price"])
        payload = {
            "address_id": address.id,
            "quote_id": quoted.data["quote_id"],
            "idempotency_key": "checkout-attempt-1",
        }
        placed = self.client.post(reverse("mobile-shop-checkout"), payload, format="json")
        repeated = self.client.post(reverse("mobile-shop-checkout"), payload, format="json")
        self.assertEqual(placed.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.data["duplicate"])
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)

    @override_settings(MOBILE_COD_MAX_TOTAL="1.00")
    @patch("payments.services.create_razorpay_order", return_value={"id": "order_native"})
    def test_native_checkout_reuses_order_and_provider_on_retry(self, create_provider):
        address = Address.objects.create(user=self.user, full_name="Buyer", phone="9876543210", address_line_1="Road", city="Town", state="State", pincode="243638", address_type="Home")
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.variant.product, variant=self.variant, quantity=1)
        quoted = self.client.post(reverse("mobile-checkout-quote", kwargs={"kind": "shop"}), {"address_id": address.pk}, format="json")
        payload = {"address_id": address.pk, "quote_id": quoted.data["quote_id"], "idempotency_key": "native-create", "payment_method": "online"}
        first = self.client.post(reverse("mobile-shop-checkout"), payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["razorpay"]["order_id"], "order_native")
        # A restarted submission with the same quote must still reuse the order.
        second = self.client.post(reverse("mobile-shop-checkout"), {**payload, "idempotency_key": "new-client-key"}, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["id"], first.data["id"])
        self.assertEqual(second.data["razorpay"]["order_id"], "order_native")
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.variant.refresh_from_db(); self.assertEqual(self.variant.stock, 4)
        create_provider.assert_called_once()

    @override_settings(MOBILE_COD_MAX_TOTAL="1.00")
    def test_quote_reports_cod_ineligibility_and_checkout_enforces_it(self):
        address = Address.objects.create(user=self.user, full_name="Buyer", phone="9876543210", address_line_1="1 Main Road", city="Sahaswan", state="Uttar Pradesh", pincode="243638", address_type="Home")
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.variant.product, variant=self.variant, quantity=1)
        quoted = self.client.post(reverse("mobile-checkout-quote", kwargs={"kind":"shop"}), {"address_id":address.id}, format="json")
        self.assertFalse(quoted.data["price"]["cod_eligible"])
        placed = self.client.post(reverse("mobile-shop-checkout"), {"address_id":address.id, "quote_id":quoted.data["quote_id"], "idempotency_key":"cod-blocked"}, format="json")
        self.assertEqual(placed.status_code, 409)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)

    def test_local_service_catalogs_are_public(self):
        self.client.force_authenticate(user=None)
        for route in (
            "mobile-restaurants", "mobile-grocery-stores",
            "mobile-grocery-categories", "mobile-grocery-products",
        ):
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_food_cart_is_persistent_and_rejects_mixed_restaurants(self):
        owner = User.objects.create_user("food-owner")
        seller = SellerProfile.objects.create(user=owner, store_name="Test Kitchen", business_segment="food", business_category="Restaurant", status="approved")
        restaurant = Restaurant.objects.create(seller=seller, name="Test Kitchen", pincode="243638", accepts_orders=True)
        section = MenuSection.objects.create(restaurant=restaurant, name="Meals")
        item = MenuItem.objects.create(restaurant=restaurant, section=section, name="Veg Meal")
        option = MenuItemOption.objects.create(item=item, name="Regular", price="120.00")
        added = self.client.post(reverse("mobile-food-cart-add"), {"option_id": option.id, "quantity": 2}, format="json")
        self.assertEqual(added.status_code, 201)
        self.assertEqual(self.client.get(reverse("mobile-food-cart")).data["item_count"], 2)
        invalid = self.client.post(reverse("mobile-food-cart-add"), {"option_id": option.id, "quantity": "many"}, format="json")
        self.assertEqual(invalid.status_code, 400)

        other_owner = User.objects.create_user("other-food-owner")
        other_seller = SellerProfile.objects.create(user=other_owner, store_name="Other Kitchen", business_segment="food", business_category="Restaurant", status="approved")
        other_restaurant = Restaurant.objects.create(seller=other_seller, name="Other Kitchen", pincode="243638", accepts_orders=True)
        other_section = MenuSection.objects.create(restaurant=other_restaurant, name="Meals")
        other_item = MenuItem.objects.create(restaurant=other_restaurant, section=other_section, name="Rice Bowl")
        other_option = MenuItemOption.objects.create(item=other_item, name="Regular", price="90.00")
        rejected = self.client.post(reverse("mobile-food-cart-add"), {"option_id": other_option.id}, format="json")
        self.assertEqual(rejected.status_code, 409)
        self.assertTrue(rejected.data["replace_required"])

    def test_grocery_cart_uses_database_and_enforces_stock(self):
        owner = User.objects.create_user("grocery-owner")
        seller = SellerProfile.objects.create(user=owner, store_name="Local Store", business_segment="grocery", business_category="Grocery", status="approved")
        store = GroceryStore.objects.create(seller=seller, name="Local Store", address="Main Road", pincode="243638", phone="9999999999", accepts_orders=True)
        category = GroceryCategory.objects.create(name="Staples", slug="staples")
        product = GroceryProduct.objects.create(store=store, category=category, name="Atta", unit="5 kg", mrp="300.00", price="250.00", stock=3)
        added = self.client.post(reverse("mobile-grocery-cart-add"), {"product_id": product.id, "quantity": 2}, format="json")
        self.assertEqual(added.status_code, 201)
        row_id = added.data["items"][0]["id"]
        rejected = self.client.patch(reverse("mobile-grocery-cart-item", kwargs={"item_id": row_id}), {"quantity": 4}, format="json")
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(self.client.get(reverse("mobile-grocery-cart")).data["item_count"], 2)
