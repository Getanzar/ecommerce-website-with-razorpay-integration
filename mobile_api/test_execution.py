from unittest.mock import patch
import requests
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from . import test_partners as fixtures
from .models import SellerCase, DeliveryEvidence, AccountDeletionRequest, DeviceSession, PushDevice
from .case_services import prepare_case, submit_case_refund
from .deletion import execute_deletion
from .authentication import issue_session
from payments.services import create_payment_transaction


class CaseExecutionTests(APITestCase):
    setUp = fixtures.PartnerApiTests.setUp
    login = fixtures.PartnerApiTests.login
    url = fixtures.PartnerApiTests.url

    def case(self):
        return SellerCase.objects.create(seller=self.seller, order_kind="shop", order_id=self.order.pk, order_item_id=self.item.pk, kind="cancellation", reason="Customer requested cancellation")

    def test_cancellation_is_item_scoped_and_idempotent(self):
        case = self.case()
        prepare_case(case.pk)
        prepare_case(case.pk)
        self.item.refresh_from_db(); self.other_item.refresh_from_db(); self.variant.refresh_from_db()
        self.assertEqual(self.item.fulfillment_status, "cancelled")
        self.assertEqual(self.other_item.fulfillment_status, "new")
        self.assertEqual(self.variant.stock, 6)

    def test_seller_cannot_request_case_for_foreign_item(self):
        self.login(self.seller_user)
        response = self.client.post(self.url(f"seller/shop/orders/{self.other_item.pk}/cases/"), {"kind": "cancellation", "reason": "Not my item"}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_duplicate_request_returns_same_case(self):
        self.login(self.seller_user)
        path = self.url(f"seller/shop/orders/{self.item.pk}/cases/")
        first = self.client.post(path, {"kind": "cancellation", "reason": "Please cancel"}, format="json")
        second = self.client.post(path, {"kind": "cancellation", "reason": "Please cancel"}, format="json")
        self.assertEqual(first.data["id"], second.data["id"])

    def test_requests_for_two_items_do_not_share_case(self):
        from orders.models import OrderItem
        second_item = OrderItem.objects.create(order=self.order, product=self.product, variant=self.variant, product_name="Another shirt", quantity=1, price="110", seller_unit_price="100")
        self.login(self.seller_user)
        responses = [self.client.post(self.url(f"seller/shop/orders/{pk}/cases/"), {"kind": "cancellation", "reason": "Please cancel"}, format="json") for pk in (self.item.pk, second_item.pk)]
        self.assertTrue(all(response.status_code == 201 for response in responses))
        self.assertNotEqual(responses[0].data["id"], responses[1].data["id"])

    @patch("mobile_api.case_services.requests.post")
    def test_uncertain_refund_reserves_balance_and_reuses_key(self, post):
        self.order.payment_method = "online"; self.order.payment_status = "Paid"; self.order.save()
        payment = create_payment_transaction(self.order, "order_case")
        payment.status = "captured"; payment.provider_payment_id = "pay_case"; payment.save()
        case = prepare_case(self.case().pk)
        post.side_effect = requests.Timeout("uncertain")
        with self.assertRaises(ValidationError):
            submit_case_refund(case)
        key = post.call_args.kwargs["headers"]["X-Refund-Idempotency"]
        case.refund.refresh_from_db()
        self.assertEqual(case.refund.status, "requested")
        post.side_effect = None
        post.return_value.json.return_value = {"id": "refund_case", "amount": int(case.refund.amount * 100), "status": "processed"}
        submit_case_refund(prepare_case(case.pk))
        self.assertEqual(post.call_args.kwargs["headers"]["X-Refund-Idempotency"], key)
        self.assertEqual(payment.refunds.count(), 1)
        case.refresh_from_db(); self.assertEqual(case.status, "resolved")

    def test_rider_evidence_ownership_and_validation(self):
        self.job.agent = self.agent; self.job.status = "out_for_delivery"; self.job.save()
        self.login(self.other_agent.user)
        path = self.url(f"rider/jobs/{self.job.pk}/evidence/")
        self.assertEqual(self.client.post(path, {"reason": "customer_unavailable"}).status_code, 404)
        self.login(self.agent_user)
        self.assertEqual(self.client.post(path, {"reason": "customer_unavailable"}).status_code, 201)
        self.job.refresh_from_db(); self.assertEqual(self.job.status, "out_for_delivery")
        image = SimpleUploadedFile("bad.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.client.post(path, {"photo": image}, format="multipart").status_code, 400)
        self.assertEqual(DeliveryEvidence.objects.filter(delivery=self.job).count(), 1)


class AccountExecutionTests(APITestCase):
    def test_deletion_erases_account_and_revokes_credentials(self):
        user = User.objects.create_user("erase-me", email="private@example.com", first_name="Private")
        issue_session(user)
        PushDevice.objects.create(user=user, expo_push_token="ExpoPushToken[test]")
        row = AccountDeletionRequest.objects.create(user=user)
        execute_deletion(row.pk)
        user.refresh_from_db(); row.refresh_from_db()
        self.assertFalse(user.is_active); self.assertEqual(user.email, "")
        self.assertEqual(row.status, "Completed")
        self.assertFalse(PushDevice.objects.filter(user=user).exists())
        self.assertFalse(DeviceSession.objects.filter(user=user, revoked_at__isnull=True).exists())

    def test_staff_deletion_is_rejected(self):
        user = User.objects.create_user("keep-admin", is_staff=True)
        row = AccountDeletionRequest.objects.create(user=user)
        with self.assertRaises(ValidationError):
            execute_deletion(row.pk)
        user.refresh_from_db(); self.assertTrue(user.is_active)
