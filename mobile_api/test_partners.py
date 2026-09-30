from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from delivery.models import DeliveryAgentProfile, DeliveryEarning, LocalDelivery
from food.models import FoodOrder, Restaurant
from orders.models import Order, OrderItem, SellerSettlement
from products.models import Category, Product, ProductColor, ProductVariant


class PartnerApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.buyer = User.objects.create_user("buyer")
        self.seller_user = User.objects.create_user("seller")
        self.seller = SellerProfile.objects.create(user=self.seller_user, store_name="My shop", business_segment="shop", business_category="Clothing", status="approved")
        self.other_seller = SellerProfile.objects.create(user=User.objects.create_user("other-seller"), store_name="Other shop", business_segment="shop", business_category="Clothing", status="approved")
        category = Category.objects.create(name="Clothes", slug="clothes")
        self.product = Product.objects.create(seller=self.seller, category=category, name="Shirt", price="100", moderation_status="approved")
        self.other_product = Product.objects.create(seller=self.other_seller, category=category, name="Other shirt", price="200", moderation_status="approved")
        color = ProductColor.objects.create(product=self.product, name="Blue")
        self.variant = ProductVariant.objects.create(product=self.product, color=color, size="M", stock=5)
        self.order = Order.objects.create(user=self.buyer, full_name="Buyer", phone="9876543210", address="Private road", city="Sahaswan", state="UP", pincode="243638", total_price="330", status="Processing", payment_method="cod", payment_status="Pending")
        self.item = OrderItem.objects.create(order=self.order, product=self.product, variant=self.variant, product_name="Shirt", quantity=1, price="110", seller_unit_price="100")
        self.other_item = OrderItem.objects.create(order=self.order, product=self.other_product, product_name="Other shirt", quantity=1, price="220", seller_unit_price="200")
        self.agent_user = User.objects.create_user("rider")
        self.agent = DeliveryAgentProfile.objects.create(user=self.agent_user, full_name="Rider", pincode="243638", status="approved", is_online=True)
        self.other_agent = DeliveryAgentProfile.objects.create(user=User.objects.create_user("other-rider"), full_name="Other rider", pincode="243638", status="approved", is_online=True)
        self.job = LocalDelivery.objects.create(parcel_order=self.order, parcel_seller=self.seller, pincode="243638", pickup_name="My shop", pickup_address="Market", customer_name="Buyer", customer_phone="9876543210", delivery_address="Private road", agent_earning="40", collection_amount="110")

    def login(self, user):
        self.client.force_authenticate(user=user)

    def url(self, suffix):
        return "/api/v1/partners/" + suffix

    def test_anonymous_and_customer_cannot_access_partner_records(self):
        self.assertEqual(self.client.get(self.url("seller/shop/orders/")).status_code, 401)
        self.login(self.buyer)
        self.assertEqual(self.client.get(self.url("seller/shop/orders/")).status_code, 404)
        self.assertEqual(self.client.get(self.url("rider/jobs/")).status_code, 404)

    def test_roles_are_read_only_and_pending_account_is_blocked(self):
        self.login(self.seller_user)
        self.assertEqual(self.client.get(self.url("roles/")).data["seller"]["status"], "approved")
        self.seller.status = "pending"
        self.seller.save()
        self.assertEqual(self.client.get(self.url("seller/shop/orders/")).status_code, 403)
        self.assertEqual(self.client.patch(self.url("roles/"), {"status": "approved"}).status_code, 405)

    def test_seller_orders_do_not_leak_other_sellers_items(self):
        self.login(self.seller_user)
        response = self.client.get(self.url("seller/shop/orders/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["items"][0]["name"], "Shirt")
        self.assertEqual(response.data["results"][0]["amount"], "100.00")
        response = self.client.patch(self.url(f"seller/shop/orders/{self.other_item.pk}/"), {"status": "accepted"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_fulfillment_cannot_skip_stages_or_fulfill_unpaid_order(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/orders/{self.item.pk}/")
        self.assertEqual(self.client.patch(path, {"status": "shipped"}, format="json").status_code, 400)
        self.order.payment_method = "online"
        self.order.save()
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 400)
        self.order.payment_status = "Paid"
        self.order.save()
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(path, {"status": "packed"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(path, {"status": "shipped", "courier": "Carrier", "tracking_number": "123"}, format="json").status_code, 400)

    def test_catalog_stock_and_moderation_guards(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/catalog/{self.product.pk}/")
        self.assertEqual(self.client.patch(path, {"stock": -1, "variant_id": self.variant.pk}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(path, {"stock": 8, "variant_id": self.variant.pk}, format="json").status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)
        self.product.moderation_status = "pending"
        self.product.save()
        self.assertEqual(self.client.patch(path, {"active": True}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(self.url(f"seller/shop/catalog/{self.other_product.pk}/"), {"active": False}, format="json").status_code, 404)

    def test_seller_payouts_are_scoped(self):
        for seller in (self.seller, self.other_seller):
            SellerSettlement.objects.create(seller=seller, order=self.order, gross_amount=100, commission_amount=10, net_amount=100, payment_method="cod", scheduled_for=timezone.now())
        self.login(self.seller_user)
        response = self.client.get(self.url("seller/shop/payouts/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_available_jobs_hide_customer_contact(self):
        self.login(self.agent_user)
        data = self.client.get(self.url("rider/jobs/?scope=available")).data["results"][0]
        self.assertEqual(data["customer_phone"], "")
        self.assertEqual(data["delivery_address"], "")
        self.assertNotIn("otp", data)
        self.assertEqual(data["net"], "36.00")

    def test_offline_and_wrong_pincode_cannot_claim_jobs(self):
        self.login(self.agent_user)
        self.agent.is_online = False
        self.agent.save()
        self.assertEqual(self.client.post(self.url(f"rider/jobs/{self.job.pk}/accept/")).status_code, 403)
        self.agent.is_online = True
        self.agent.pincode = "110001"
        self.agent.save()
        self.assertEqual(self.client.post(self.url(f"rider/jobs/{self.job.pk}/accept/")).status_code, 404)

    def test_claim_conflict_and_ownership(self):
        self.login(self.agent_user)
        path = self.url(f"rider/jobs/{self.job.pk}/accept/")
        self.assertEqual(self.client.post(path).status_code, 200)
        self.assertEqual(self.client.post(path).status_code, 200)
        self.login(self.other_agent.user)
        self.assertEqual(self.client.post(path).status_code, 409)
        self.assertEqual(self.client.patch(self.url(f"rider/jobs/{self.job.pk}/status/"), {"status": "accepted"}, format="json").status_code, 404)

    def test_suspended_rider_cannot_update_active_job(self):
        self.job.agent = self.agent
        self.job.status = "assigned"
        self.job.save()
        self.agent.status = "suspended"
        self.agent.save()
        self.login(self.agent_user)
        self.assertEqual(self.client.patch(self.url(f"rider/jobs/{self.job.pk}/status/"), {"status": "accepted"}, format="json").status_code, 403)

    @patch("delivery.services.send_mail")
    def test_rider_lifecycle_otp_cash_and_idempotent_earning(self, send):
        self.login(self.agent_user)
        base = self.url(f"rider/jobs/{self.job.pk}/")
        self.client.post(base + "accept/")
        self.assertEqual(self.client.patch(base + "status/", {"status": "out_for_delivery"}, format="json").status_code, 400)
        for status in ("accepted", "picked_up", "out_for_delivery"):
            self.assertEqual(self.client.patch(base + "status/", {"status": status}, format="json").status_code, 200)
        self.job.refresh_from_db()
        self.job.delivery_otp_hash = make_password("123456")
        self.job.otp_expires_at = timezone.now() + timedelta(minutes=10)
        self.job.save()
        self.assertEqual(self.client.post(base + "complete/", {"otp": "999999", "cash_collected": True}, format="json").status_code, 400)
        self.assertEqual(self.client.post(base + "complete/", {"otp": "123456"}, format="json").status_code, 400)
        for _ in range(2):
            self.assertEqual(self.client.post(base + "complete/", {"otp": "123456", "cash_collected": True}, format="json").status_code, 200)
        self.assertEqual(DeliveryEarning.objects.filter(delivery=self.job).count(), 1)
        self.assertEqual(DeliveryEarning.objects.get(delivery=self.job).status, "pending")

    def test_location_validation_and_retention(self):
        self.login(self.agent_user)
        self.job.agent = self.agent
        self.job.status = "accepted"
        self.job.save()
        path = self.url(f"rider/jobs/{self.job.pk}/location/")
        self.assertEqual(self.client.post(path, {"latitude": "NaN", "longitude": "79", "accuracy": 10}, format="json").status_code, 400)
        self.assertEqual(self.client.post(path, {"latitude": "28.123456", "longitude": "79.123456", "accuracy": 10}, format="json").status_code, 200)
        self.job.status = "delivered"
        self.job.save()
        self.assertEqual(self.client.post(path, {"latitude": "28", "longitude": "79", "accuracy": 10}, format="json").status_code, 400)
        history = self.client.get(self.url("rider/jobs/?scope=history")).data["results"][0]
        self.assertEqual(history["customer_phone"], "")

    def test_application_creates_pending_role_on_current_account(self):
        self.login(self.buyer)
        response = self.client.post(self.url("applications/rider/"), {"full_name": "New rider", "phone": "9999999999", "address": "Market", "city": "Sahaswan", "state": "UP", "pincode": "243638", "vehicle_type": "bicycle", "aadhaar_last4": "1234", "status": "approved", "payouts_enabled": True}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        rider = DeliveryAgentProfile.objects.get(user=self.buyer)
        self.assertEqual(rider.status, "pending")
        self.assertFalse(rider.payouts_enabled)
        self.assertEqual(self.client.post(self.url("applications/rider/"), {}).status_code, 403)

    def test_product_edit_is_scoped_and_returns_to_moderation(self):
        self.login(self.seller_user)
        self.assertEqual(self.client.get(self.url(f"seller/products/{self.other_product.pk}/edit/")).status_code, 404)
        response = self.client.post(self.url(f"seller/products/{self.product.pk}/edit/"), {"name": "Updated shirt", "description": "Cotton", "price": "120.00", "gst_rate": "5.00", "package_weight_grams": 500, "package_length_cm": 10, "package_width_cm": 10, "package_height_cm": 10}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.moderation_status, "pending")
        self.assertFalse(self.product.is_active)

    def test_food_orders_and_availability(self):
        self.seller.business_segment = 'food'
        self.seller.business_category = "Restaurant"
        self.seller.save()
        restaurant = Restaurant.objects.create(seller=self.seller, name="Kitchen")
        order = FoodOrder.objects.create(user=self.buyer, restaurant=restaurant, subtotal=100, total=100, payment_method="cod", pincode="243638")
        self.login(self.seller_user)
        self.assertEqual(self.client.get(self.url("seller/food/orders/")).status_code, 200)
        self.assertEqual(self.client.patch(self.url(f"seller/food/orders/{order.pk}/"), {"status": "accepted"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(self.url("seller/food/availability/"), {"accepts_orders": False}, format="json").status_code, 200)
        restaurant.refresh_from_db()
        self.assertFalse(restaurant.accepts_orders)

    def test_seller_application_schema_has_no_privileged_fields(self):
        self.login(self.buyer)
        response = self.client.get(self.url("applications/seller/"))
        self.assertEqual(response.status_code, 200)
        fields = {row["name"] for row in response.data["fields"]}
        self.assertIn("gps_captured_at", fields)
        self.assertNotIn("status", fields)
        self.assertNotIn("payouts_enabled", fields)

    def test_menu_creation_and_variant_edit(self):
        for seller in (self.seller, self.other_seller):
            seller.business_segment = 'food'
            seller.business_category = "Food"
            seller.save()
        from food.models import MenuItem, MenuItemOption
        Restaurant.objects.create(seller=self.seller, name="Kitchen")
        self.login(self.seller_user)
        response = self.client.post(self.url("seller/food/products/new/"), {"name": "Dosa", "section_name": "Breakfast", "food_type": "veg", "option_name": "Regular", "option_price": "80.00", "is_available": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        item = MenuItem.objects.get(name="Dosa")
        option = MenuItemOption.objects.get(item=item)
        response = self.client.post(self.url(f"seller/food/products/{item.pk}/variants/{option.pk}/"), {"name": "Regular", "price": "90", "is_available": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.login(self.other_seller.user)
        self.assertEqual(self.client.get(self.url(f"seller/food/products/{item.pk}/edit/")).status_code, 404)

    def test_variant_changes_require_approval_and_reject_foreign_colors(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/products/{self.product.pk}/variants/new/")
        foreign_color = ProductColor.objects.create(product=self.other_product, name="Red")
        data = {"color": foreign_color.pk, "size": "L", "stock": 3, "price": "110", "is_active": True}
        self.assertEqual(self.client.post(path, data, format="json").status_code, 400)
        data["color"] = self.variant.color_id
        self.assertEqual(self.client.post(path, data, format="json").status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertEqual(self.product.moderation_status, "pending")

    @patch("accounts.payouts.provision_seller_payout_account")
    def test_payout_setup_requires_matching_bank_numbers_and_disables_payouts(self, provider):
        self.seller.payouts_enabled = True
        self.seller.save()
        self.login(self.seller_user)
        data = {"bank_account_holder": "Seller", "bank_account_number": "123456789012", "confirm_bank_account_number": "999999999999", "bank_ifsc_code": "SBIN0001234"}
        self.assertEqual(self.client.post(self.url("payout-setup/seller/"), data, format="json").status_code, 400)
        provider.assert_not_called()
        data["confirm_bank_account_number"] = data["bank_account_number"]
        self.assertEqual(self.client.post(self.url("payout-setup/seller/"), data, format="json").status_code, 200)
        self.seller.refresh_from_db()
        self.assertFalse(self.seller.payouts_enabled)
        self.assertEqual(self.seller.bank_account_last4, "9012")
