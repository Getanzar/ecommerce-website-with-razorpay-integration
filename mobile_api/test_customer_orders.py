from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import SellerProfile
from food.models import FoodOrder, Restaurant
from groceries.models import GroceryOrder, GroceryStore
from orders.models import Order, OrderItem, ReturnRequest
from products.models import Category, Product, ProductReview


class CustomerOrderTests(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user("buyer")
        self.other = User.objects.create_user("another-buyer")
        seller = SellerProfile.objects.create(user=User.objects.create_user("seller"), store_name="Store", status="approved")
        category = Category.objects.create(name="Clothing", slug="clothing")
        product = Product.objects.create(name="Shirt", category=category, seller=seller, price=100)
        self.order = Order.objects.create(user=self.user, full_name="Buyer <name>", phone="9876543210", total_price=100, status="Delivered", payment_method="cod", payment_status="Pending", delivered_at=timezone.now())
        self.item = OrderItem.objects.create(order=self.order, product=product, product_name="Shirt", quantity=2, price=50)
        self.client.force_authenticate(self.user)
        self.experience_url = f"/api/v1/orders/shop/{self.order.pk}/experience/"
        self.review_url = f"/api/v1/order-items/{self.item.pk}/review/"
        self.return_url = f"/api/v1/orders/shop/{self.order.pk}/returns/"
        self.invoice_url = f"/api/v1/orders/shop/{self.order.pk}/invoice/"
        self.seller = seller

    def test_review_requires_delivered_purchase(self):
        self.order.status = "Processing"
        self.order.save()
        response = self.client.post(self.review_url, {"rating": 5, "review": "Excellent shirt"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProductReview.objects.exists())

    def test_review_update_is_unique_verified_and_moderated(self):
        for rating in (5, 4):
            response = self.client.post(self.review_url, {"rating": rating, "review": "Comfortable shirt", "is_approved": True}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProductReview.objects.count(), 1)
        review = ProductReview.objects.get()
        self.assertEqual(review.rating, 4)
        self.assertFalse(review.is_approved)
        self.assertTrue(review.is_verified_purchase)

    def test_review_rating_is_bounded(self):
        self.assertEqual(self.client.post(self.review_url, {"rating": 6, "review": "Great shirt"}, format="json").status_code, 400)

    def test_customer_cannot_access_another_customers_records(self):
        self.client.force_authenticate(self.other)
        for path in (self.experience_url, self.invoice_url, self.review_url):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post(self.return_url, {}, format="json").status_code, 404)
        self.assertEqual(self.client.post(self.review_url, {"rating": 5, "review": "Great shirt"}, format="json").status_code, 404)

    def test_return_uses_marketplace_return_model_and_is_not_duplicated(self):
        data = {"order_item_id": self.item.pk, "reason": "Wrong Size", "description": "The shirt is too small"}
        first = self.client.post(self.return_url, data, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(self.client.post(self.return_url, data, format="json").status_code, 409)
        self.assertEqual(ReturnRequest.objects.count(), 1)
        experience = self.client.get(self.experience_url).data
        self.assertFalse(experience["items"][0]["can_return"])
        self.assertEqual(experience["returns"][0]["refund_status"], "Pending")

    def test_return_window_and_item_ownership(self):
        other_order = Order.objects.create(user=self.other, total_price=100)
        other_item = OrderItem.objects.create(order=other_order, product=self.item.product, quantity=1, price=100)
        data = {"order_item_id": other_item.pk, "reason": "Other", "description": "Return this shirt"}
        self.assertEqual(self.client.post(self.return_url, data, format="json").status_code, 404)
        self.order.delivered_at = timezone.now() - timedelta(days=30)
        self.order.save()
        data["order_item_id"] = self.item.pk
        self.assertEqual(self.client.post(self.return_url, data, format="json").status_code, 400)

    def test_return_rejects_non_image_evidence(self):
        data = {"order_item_id": self.item.pk, "reason": "Other", "description": "Return this shirt", "image": SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")}
        self.assertEqual(self.client.post(self.return_url, data, format="multipart").status_code, 400)
        self.assertFalse(ReturnRequest.objects.exists())

    def test_whole_order_return_blocks_item_return(self):
        ReturnRequest.objects.create(order=self.order, user=self.user, reason="Other")
        data = {"order_item_id": self.item.pk, "reason": "Other", "description": "Return this shirt"}
        self.assertEqual(self.client.post(self.return_url, data, format="json").status_code, 409)

    def test_invoice_returns_private_pdf(self):
        response = self.client.get(self.invoice_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_invoice_is_unavailable_before_payment_or_delivery(self):
        self.order.status = "Processing"
        self.order.save()
        self.assertEqual(self.client.get(self.invoice_url).status_code, 400)

    def test_food_and_grocery_invoice_and_experience(self):
        restaurant = Restaurant.objects.create(seller=self.seller, name="Kitchen")
        store = GroceryStore.objects.create(seller=self.seller, name="Grocer")
        for kind, model, owner in (("food", FoodOrder, {"restaurant": restaurant}), ("grocery", GroceryOrder, {"store": store})):
            order = model.objects.create(user=self.user, subtotal=100, total=100, payment_method="online", payment_status="Paid", **owner)
            response = self.client.get(f"/api/v1/orders/{kind}/{order.pk}/invoice/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b"%PDF"))
            response = self.client.get(f"/api/v1/orders/{kind}/{order.pk}/experience/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["items"], [])

    def test_invalid_order_type_is_rejected(self):
        self.assertEqual(self.client.get(f"/api/v1/orders/unknown/{self.order.pk}/experience/").status_code, 400)

    def test_support_cannot_link_another_customers_order(self):
        other_order = Order.objects.create(user=self.other, total_price=100)
        response = self.client.post("/api/v1/support/", {"reason": "Where is my order", "message": "Please investigate this order", "order_kind": "shop", "order_id": other_order.pk}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_support_inbox_and_replies_are_owned(self):
        response = self.client.post("/api/v1/support/", {"reason": "Delivery question", "message": "Please explain delivery timing"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(self.client.post(f"/api/v1/support/{pk}/replies/", {"message": "Here are more details", "is_staff": True}, format="json").status_code, 201)
        data = self.client.get("/api/v1/support/").data
        self.assertEqual(len(data), 1)
        self.assertFalse(data[0]["replies"][0]["is_staff"])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/v1/support/").data, [])
        self.assertEqual(self.client.post(f"/api/v1/support/{pk}/replies/", {"message": "Hello"}, format="json").status_code, 404)

    def test_generic_support_cannot_bypass_return_workflow(self):
        response = self.client.post("/api/v1/support/", {"reason": "Wrong size", "message": "Please return this item", "request_type": "return", "order_id": self.order.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_notification_preferences_reject_string_booleans(self):
        self.assertEqual(self.client.patch("/api/v1/account/notifications/", {"promotions": "false"}, format="json").status_code, 400)

    def test_weak_password_change_is_rejected(self):
        self.user.set_password("Existing-strong-secret-284")
        self.user.save()
        response = self.client.post("/api/v1/auth/password/change/", {"current_password": "Existing-strong-secret-284", "new_password": "123"}, format="json")
        self.assertEqual(response.status_code, 400)
