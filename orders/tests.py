from datetime import timedelta
from decimal import Decimal
import hashlib
import hmac
import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Order, SellerSettlement


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False, RETURN_WINDOW_DAYS=7)
class ReturnWindowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("return-customer", password="test-password")
        self.order = Order.objects.create(
            user=self.customer,
            full_name="Return Customer",
            phone="9999999999",
            address="Market Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price=Decimal("100.00"),
            status="Delivered",
            payment_method="online",
            payment_status="Paid",
            delivered_at=timezone.now() - timedelta(days=2),
        )
        self.client.login(username="return-customer", password="test-password")

    def test_delivered_order_can_enter_return_flow_within_seven_days(self):
        response = self.client.get(reverse("return_order", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.order.can_request_return)

    def test_expired_return_window_is_rejected(self):
        self.order.delivered_at = timezone.now() - timedelta(days=8)
        self.order.save(update_fields=["delivered_at"])

        response = self.client.get(reverse("return_order", args=[self.order.pk]), follow=True)
        self.assertRedirects(response, reverse("order_detail", args=[self.order.pk]))
        self.assertContains(response, "7-day return window")
        self.order.refresh_from_db()
        self.assertFalse(self.order.can_request_return)

@override_settings(
    ROOT_URLCONF="config.urls",
    SECURE_SSL_REDIRECT=False,
    RAZORPAYX_WEBHOOK_SECRET="test-razorpayx-webhook-secret",
)
class RazorpayXWebhookTests(TestCase):
    def _payload(
        self,
        payout_id="pout_test_123",
        status="processed",
        reference_id=None,
    ):
        entity = {
            "id": payout_id,
            "status": status,
        }

        if reference_id is not None:
            entity["reference_id"] = reference_id

        return {
            "event": f"payout.{status}",
            "payload": {
                "payout": {
                    "entity": entity,
                }
            },
        }

    def _post(self, payload, event_id="event_test_123", valid_signature=True):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        secret = (
            "test-razorpayx-webhook-secret"
            if valid_signature
            else "wrong-secret"
        )

        signature = hmac.new(
            secret.encode(),
            raw,
            hashlib.sha256,
        ).hexdigest()

        return self.client.post(
            reverse("razorpayx_webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )

    def test_valid_signed_webhook_is_accepted(self):
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 204)

    def test_invalid_signature_is_rejected(self):
        response = self._post(
            self._payload(),
            valid_signature=False,
        )
        self.assertEqual(response.status_code, 400)

    def test_processed_duplicate_is_idempotent(self):
        payload = self._payload()

        first = self._post(payload, event_id="event_duplicate")
        second = self._post(payload, event_id="event_duplicate")

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 204)

        from payments.models import PaymentWebhookEvent

        self.assertEqual(
            PaymentWebhookEvent.objects.filter(
                provider="razorpayx",
                event_id="event_duplicate",
            ).count(),
            1,
        )

    def test_reused_event_id_with_different_payload_is_rejected(self):
        first = self._post(
            self._payload(status="processed"),
            event_id="event_reused",
        )

        second = self._post(
            self._payload(status="reversed"),
            event_id="event_reused",
        )

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 400)

    def test_processed_payout_marks_delivery_earning_paid(self):
        from accounts.models import SellerProfile
        from delivery.models import (
            DeliveryAgentProfile,
            DeliveryEarning,
            LocalDelivery,
        )

        # Create delivery agent.
        agent_user = User.objects.create_user(
            username="payout-agent",
            email="agent@example.com",
        )

        agent = DeliveryAgentProfile.objects.create(
            user=agent_user,
            full_name="Payout Agent",
            phone="9999999999",
            address="Market Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            vehicle_type="motorcycle",
            aadhaar_last4="1234",
            status="approved",
        )

        # Create customer.
        customer = User.objects.create_user(
            username="payout-customer",
            email="customer@example.com",
        )

        # Create seller required for a parcel LocalDelivery.
        seller_user = User.objects.create_user(
            username="payout-seller-webhook",
            email="payout-seller@example.com",
        )

        seller = SellerProfile.objects.create(
            user=seller_user,
            store_name="Webhook Payout Test Store",
            legal_business_name="Webhook Payout Test Store",
            business_segment="shop",
            business_phone="7777777777",
            business_address="Sahaswan",
            business_pincode="243638",
            status="approved",
        )

        # Create parcel order.
        order = Order.objects.create(
            user=customer,
            full_name="Payout Customer",
            phone="8888888888",
            address="Customer Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price=Decimal("500.00"),
            payment_method="online",
            payment_status="Paid",
        )

        # Create local delivery linked to both parcel order and seller.
        delivery = LocalDelivery.objects.create(
            parcel_order=order,
            parcel_seller=seller,
            agent=agent,
            pincode="243638",
            pickup_name="ZIYAMART",
            pickup_address="Sahaswan",
            customer_name="Payout Customer",
            customer_phone="8888888888",
            delivery_address="Customer Road",
            delivery_fee=Decimal("50.00"),
            agent_earning=Decimal("50.00"),
        )

        # Simulate a payout that has already been submitted to RazorpayX.
        earning = DeliveryEarning.objects.create(
            agent=agent,
            delivery=delivery,
            amount=Decimal("50.00"),
            status="processing",
            provider_payout_id="pout_delivery_test_123",
        )

        # Simulate RazorpayX confirming that payout was processed.
        response = self._post(
            self._payload(
                payout_id="pout_delivery_test_123",
                status="processed",
            ),
            event_id="event_delivery_paid",
        )

        self.assertEqual(response.status_code, 204)

        earning.refresh_from_db()

        self.assertEqual(earning.status, "paid")
        self.assertIsNotNone(earning.paid_at)
        self.assertEqual(earning.failure_reason, "")

    def test_webhook_recovers_seller_payout_by_reference_id_before_local_payout_id_save(self):
        from accounts.models import SellerProfile

        # Create seller.
        seller_user = User.objects.create_user(
            username="early-webhook-seller",
            email="early-webhook-seller@example.com",
        )

        seller = SellerProfile.objects.create(
            user=seller_user,
            store_name="Early Webhook Store",
            legal_business_name="Early Webhook Store",
            business_segment="shop",
            status="approved",
        )

        # Create customer and order.
        customer = User.objects.create_user(
            username="early-webhook-customer",
            email="early-webhook-customer@example.com",
        )

        order = Order.objects.create(
            user=customer,
            full_name="Early Webhook Customer",
            phone="9999999999",
            address="Customer Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price=Decimal("1000.00"),
            payment_method="online",
            payment_status="Paid",
        )

        # Important: provider_payout_id is deliberately blank.
        # This simulates RazorpayX sending its webhook before our payout
        # submission view has finished saving the returned payout ID.
        settlement = SellerSettlement.objects.create(
            seller=seller,
            order=order,
            gross_amount=Decimal("1000.00"),
            commission_amount=Decimal("100.00"),
            net_amount=Decimal("900.00"),
            payment_method="online",
            status="processing",
            scheduled_for=timezone.now(),
            provider_payout_id="",
        )

        self.assertEqual(
            settlement.payout_reference_key,
            f"general-{settlement.pk}",
        )

        response = self._post(
            self._payload(
                payout_id="pout_early_webhook_123",
                status="processed",
                reference_id=settlement.payout_reference_key,
            ),
            event_id="event_early_webhook_123",
        )

        self.assertEqual(response.status_code, 204)

        settlement.refresh_from_db()

        # The webhook must recover the settlement from reference_id.
        self.assertEqual(
            settlement.provider_payout_id,
            "pout_early_webhook_123",
        )

        self.assertEqual(settlement.status, "paid")
        self.assertEqual(settlement.failure_reason, "")
        self.assertIsNotNone(settlement.processed_at)

        from payments.models import PaymentWebhookEvent

        event = PaymentWebhookEvent.objects.get(
            provider="razorpayx",
            event_id="event_early_webhook_123",
        )

        self.assertEqual(event.status, "processed")

    def test_stale_processing_event_does_not_regress_paid_seller_settlement(self):
        from accounts.models import SellerProfile

        seller_user = User.objects.create_user(
            username="stale-event-seller",
            email="stale-event-seller@example.com",
        )

        seller = SellerProfile.objects.create(
            user=seller_user,
            store_name="Stale Event Store",
            legal_business_name="Stale Event Store",
            business_segment="shop",
            status="approved",
        )

        customer = User.objects.create_user(
            username="stale-event-customer",
            email="stale-event-customer@example.com",
        )

        order = Order.objects.create(
            user=customer,
            full_name="Stale Event Customer",
            phone="9999999999",
            address="Customer Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price=Decimal("1000.00"),
            payment_method="online",
            payment_status="Paid",
        )

        settlement = SellerSettlement.objects.create(
            seller=seller,
            order=order,
            gross_amount=Decimal("1000.00"),
            commission_amount=Decimal("100.00"),
            net_amount=Decimal("900.00"),
            payment_method="online",
            status="paid",
            scheduled_for=timezone.now(),
            provider_payout_id="pout_already_paid_123",
            processed_at=timezone.now(),
        )

        original_processed_at = settlement.processed_at

        # Simulate an older/non-terminal RazorpayX event arriving after
        # the payout has already been confirmed as processed.
        response = self._post(
            self._payload(
                payout_id="pout_already_paid_123",
                status="queued",
                reference_id=settlement.payout_reference_key,
            ),
            event_id="event_stale_queued_123",
        )

        self.assertEqual(response.status_code, 204)

        settlement.refresh_from_db()

        # A stale queued/pending event must never move a paid payout
        # backwards to processing.
        self.assertEqual(settlement.status, "paid")
        self.assertEqual(
            settlement.processed_at,
            original_processed_at,
        )

    def test_reference_id_cannot_update_settlement_with_different_payout_id(self):
        from accounts.models import SellerProfile

        seller_user = User.objects.create_user(
            username="mismatch-payout-seller",
            email="mismatch-payout-seller@example.com",
        )

        seller = SellerProfile.objects.create(
            user=seller_user,
            store_name="Mismatch Payout Store",
            legal_business_name="Mismatch Payout Store",
            business_segment="shop",
            status="approved",
        )

        customer = User.objects.create_user(
            username="mismatch-payout-customer",
            email="mismatch-payout-customer@example.com",
        )

        order = Order.objects.create(
            user=customer,
            full_name="Mismatch Customer",
            phone="9999999999",
            address="Customer Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price=Decimal("1000.00"),
            payment_method="online",
            payment_status="Paid",
        )

        settlement = SellerSettlement.objects.create(
            seller=seller,
            order=order,
            gross_amount=Decimal("1000.00"),
            commission_amount=Decimal("100.00"),
            net_amount=Decimal("900.00"),
            payment_method="online",
            status="processing",
            scheduled_for=timezone.now(),
            provider_payout_id="pout_real_123",
        )

        response = self._post(
            self._payload(
                payout_id="pout_wrong_999",
                status="processed",
                reference_id=settlement.payout_reference_key,
            ),
            event_id="event_mismatched_payout_123",
        )

        self.assertEqual(response.status_code, 204)

        settlement.refresh_from_db()

        # A reference_id must never let one RazorpayX payout
        # modify a settlement belonging to another payout.
        self.assertEqual(
            settlement.provider_payout_id,
            "pout_real_123",
        )
        self.assertEqual(settlement.status, "processing")
        self.assertIsNone(settlement.processed_at)

        from payments.models import PaymentWebhookEvent

        event = PaymentWebhookEvent.objects.get(
            provider="razorpayx",
            event_id="event_mismatched_payout_123",
        )

        self.assertEqual(event.status, "ignored")