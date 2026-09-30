from unittest.mock import patch
import requests

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from . import test_partners as fixtures
from .models import SellerCase
from food.models import FoodOrder, Restaurant
from groceries.models import GroceryCategory, GroceryOrder, GroceryOrderItem, GroceryProduct, GroceryStore
from orders.models import OrderItem, SellerSettlement
from payments.services import create_payment_transaction


class SellerOrderActionTests(APITestCase):
    setUp = fixtures.PartnerApiTests.setUp
    login = fixtures.PartnerApiTests.login
    url = fixtures.PartnerApiTests.url

    def test_merchandise_list_groups_own_items_and_detail_remains_scoped(self):
        OrderItem.objects.create(order=self.order, product=self.product, variant=self.variant,
                                product_name="Second shirt", quantity=2, price=110, seller_unit_price=100)
        self.login(self.seller_user)
        result = self.client.get(self.url("seller/shop/orders/?grouped=1"))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        summary = result.data["results"][0]
        self.assertEqual(len(summary["items"]), 2)
        self.assertEqual(float(summary["amount"]), 300)
        detail = self.client.get(self.url(f"seller/shop/orders/?order_id={self.order.pk}"))
        self.assertEqual(detail.data["count"], 2)
        self.assertEqual(self.client.get(self.url(f"seller/shop/orders/{self.other_item.pk}/")).status_code, 404)

    def test_confirm_then_cancel_restores_only_own_stock_once(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/orders/{self.item.pk}/")
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 200)
        for _ in range(2):
            response = self.client.post(path + "cancel/", {"reason": "Item unavailable"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["order"]["status"], "cancelled")
        self.variant.refresh_from_db(); self.other_item.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual(self.variant.stock, 6)
        self.assertEqual(self.other_item.fulfillment_status, "new")
        self.assertNotEqual(self.order.status, "Cancelled")
        self.assertEqual(SellerCase.objects.count(), 1)
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 400)

    def test_cancel_denies_foreign_items_category_and_invalid_reason(self):
        self.login(self.seller_user)
        self.assertEqual(self.client.post(self.url(f"seller/shop/orders/{self.other_item.pk}/cancel/"), {"reason": "Unavailable"}).status_code, 404)
        self.assertEqual(self.client.post(self.url("seller/food/orders/1/cancel/"), {"reason": "Unavailable"}).status_code, 403)
        self.assertEqual(self.client.post(self.url(f"seller/shop/orders/{self.item.pk}/cancel/"), {"reason": "no"}).status_code, 400)
        self.assertEqual(SellerCase.objects.count(), 0)

    def test_picked_up_and_paid_settlement_cannot_be_cancelled(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/orders/{self.item.pk}/cancel/")
        self.job.status = "picked_up"; self.job.save()
        self.assertEqual(self.client.post(path, {"reason": "Unavailable"}).status_code, 400)
        self.job.status = "available"; self.job.save()
        SellerSettlement.objects.create(seller=self.seller, order=self.order, gross_amount=100,
            commission_amount=10, net_amount=100, payment_method="cod", status="paid", scheduled_for=timezone.now())
        self.assertEqual(self.client.post(path, {"reason": "Unavailable"}).status_code, 400)
        self.item.refresh_from_db(); self.variant.refresh_from_db()
        self.assertEqual(self.item.fulfillment_status, "new")
        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(SellerCase.objects.count(), 0)

    def test_closed_order_and_collected_cod_cannot_be_cancelled(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/orders/{self.item.pk}/cancel/")
        self.order.status = "Delivered"; self.order.save()
        self.assertEqual(self.client.post(path, {"reason": "Unavailable"}).status_code, 400)
        self.order.status = "Processing"; self.order.payment_status = "Paid"; self.order.save()
        self.assertEqual(self.client.post(path, {"reason": "Unavailable"}).status_code, 400)

    def test_grocery_cancellation_restores_stock_once(self):
        self.seller.business_segment = 'grocery'
        self.seller.business_category = "Grocery"; self.seller.save()
        self.login(self.seller_user)
        store = GroceryStore.objects.create(seller=self.seller, name="Stock grocer")
        category = GroceryCategory.objects.create(name="Rice", slug="rice")
        product = GroceryProduct.objects.create(store=store, category=category, name="Rice", unit="1 kg", mrp=100, price=100, stock=3)
        order = GroceryOrder.objects.create(user=self.buyer, store=store, subtotal=200, total=200, payment_method="cod")
        GroceryOrderItem.objects.create(order=order, product=product, product_name="Rice", unit="1 kg", unit_price=100, quantity=2)
        path = self.url(f"seller/grocery/orders/{order.pk}/cancel/")
        for _ in range(2):
            result = self.client.post(path, {"reason": "Store is closed"})
            self.assertEqual(result.status_code, 200, result.data)
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)

    def test_unpaid_online_order_cannot_be_confirmed_or_refunded(self):
        self.order.payment_method = "online"; self.order.save()
        self.login(self.seller_user)
        path = self.url(f"seller/shop/orders/{self.item.pk}/")
        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(path + "cancel/", {"reason": "Out of stock"}).status_code, 400)
        self.assertEqual(SellerCase.objects.count(), 0)

    def test_food_and_grocery_confirm_reject_and_cancel(self):
        for kind in ("food", "grocery"):
            with self.subTest(kind=kind):
                cache.clear()
                self.seller.business_segment = kind
                self.seller.business_category = kind; self.seller.save()
                self.login(self.seller_user)
                if kind == "food":
                    store = Restaurant.objects.create(seller=self.seller, name="Kitchen")
                    model, owner = FoodOrder, {"restaurant": store}
                else:
                    store = GroceryStore.objects.create(seller=self.seller, name="Grocer")
                    model, owner = GroceryOrder, {"store": store}
                for confirm in (False, True):
                    order = model.objects.create(user=self.buyer, subtotal=100, total=100, payment_method="cod", **owner)
                    path = self.url(f"seller/{kind}/orders/{order.pk}/")
                    if confirm:
                        self.assertEqual(self.client.patch(path, {"status": "accepted"}, format="json").status_code, 200)
                    result = self.client.post(path + "cancel/", {"reason": "Not in stock"}, format="json")
                    self.assertEqual(result.status_code, 200, result.data)
                    order.refresh_from_db()
                    self.assertEqual(order.status, "cancelled")

    @patch("mobile_api.case_services.requests.post")
    def test_online_cancel_keeps_refund_intent_when_provider_times_out(self, post):
        self.login(self.seller_user)
        self.order.payment_method = "online"; self.order.payment_status = "Paid"; self.order.save()
        payment = create_payment_transaction(self.order, "order_seller_cancel")
        payment.status = "captured"; payment.provider_payment_id = "pay_cancel"; payment.save()
        post.side_effect = requests.Timeout("uncertain")
        path = self.url(f"seller/shop/orders/{self.item.pk}/cancel/")
        for _ in range(2):
            result = self.client.post(path, {"reason": "Out of stock"}, format="json")
            self.assertEqual(result.status_code, 200, result.data)
            self.assertIn("pending", result.data["message"])
        self.assertEqual(payment.refunds.count(), 1)
        self.variant.refresh_from_db(); self.assertEqual(self.variant.stock, 6)
        self.assertEqual(post.call_args_list[0].kwargs["headers"], post.call_args_list[1].kwargs["headers"])
