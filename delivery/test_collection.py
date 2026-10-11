from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import SellerProfile
from food.models import FoodOrder, Restaurant
from groceries.models import GroceryOrder, GroceryStore
from orders.models import Order
from payments.models import CODRemittance, PaymentTransaction
from .collection import CollectionError, ProviderRejected, collect_payment, collection_data
from .models import DeliveryAgentProfile, DeliveryCollection, DeliveryEarning, LocalDelivery
from .services import complete_delivery


@override_settings(RAZORPAY_KEY_ID="test", RAZORPAY_KEY_SECRET="secret", SECURE_SSL_REDIRECT=False)
class DeliveryCollectionTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("collection-customer")
        self.owner = User.objects.create_user("collection-seller")
        self.seller = SellerProfile.objects.create(user=self.owner, store_name="Store", status="approved")
        self.agent = DeliveryAgentProfile.objects.create(user=User.objects.create_user("collection-agent"), status="approved", pincode="243638")
        self.other = DeliveryAgentProfile.objects.create(user=User.objects.create_user("collection-other"), status="approved")
        self.store = GroceryStore.objects.create(seller=self.seller, name="Store")
        self.restaurant = Restaurant.objects.create(seller=self.seller, name="Kitchen")
        self.api = APIClient()
        self.api.force_authenticate(self.agent.user)

    def job(self, kind="grocery", total=100):
        common = {"user": self.customer, "payment_method": "cod", "payment_status": "Pending"}
        if kind == "grocery":
            order = GroceryOrder.objects.create(store=self.store, subtotal=total, total=total, status="ready", **common)
            link = {"grocery_order": order}
        elif kind == "food":
            order = FoodOrder.objects.create(restaurant=self.restaurant, subtotal=total, total=total, status="ready", **common)
            link = {"food_order": order}
        else:
            order = Order.objects.create(total_price=total, status="Processing", **common)
            link = {"parcel_order": order, "parcel_seller": self.seller}
        return LocalDelivery.objects.create(agent=self.agent, status="out_for_delivery", collection_amount=total, agent_earning=10, **link)

    def endpoint(self, row):
        return f"/api/v1/partners/rider/jobs/{row.pk}/payment/"

    def test_cash_collection_all_segments_is_idempotent_and_holds_earning(self):
        for kind in ("grocery", "food", "shop"):
            with self.subTest(kind=kind):
                row = self.job(kind)
                for _ in range(2):
                    result = collect_payment(row.pk, self.agent, "cash")
                    self.assertTrue(result["paid"])
                    self.assertEqual(result["method"], "cash")
                row.source_order.refresh_from_db()
                self.assertEqual(row.source_order.payment_status, "Paid")
                self.assertEqual(CODRemittance.objects.filter(delivery=row).count(), 1)
                self.assertEqual(CODRemittance.objects.get(delivery=row).amount, Decimal("100"))
                complete_delivery(row, self.agent)
                self.assertEqual(DeliveryEarning.objects.get(delivery=row).status, "pending")

    def test_completion_rejects_uncollected_cod(self):
        row = self.job()
        with self.assertRaises(CollectionError):
            complete_delivery(row, self.agent)
        row.refresh_from_db()
        self.assertEqual(row.status, "out_for_delivery")
        self.assertFalse(DeliveryEarning.objects.exists())

    def test_cash_requires_confirmation_and_assigned_agent(self):
        row = self.job()
        self.assertEqual(self.api.post(self.endpoint(row), {"action": "cash"}, format="json").status_code, 400)
        self.api.force_authenticate(self.other.user)
        self.assertEqual(self.api.post(self.endpoint(row), {"action": "cash", "confirmed": True}, format="json").status_code, 404)
        self.client.force_login(self.other.user)
        self.assertEqual(self.client.get(reverse("delivery_payment", args=[row.pk])).status_code, 404)

    @patch("delivery.collection.provider")
    def test_qr_exact_amount_capture_all_segments_and_online_earning(self, provider):
        for kind in ("grocery", "food", "shop"):
            with self.subTest(kind=kind):
                row = self.job(kind)
                qr = {"id": f"qr_{row.pk}", "image_url": "https://rzp.io/i/qr", "payment_amount": 10000}
                provider.return_value = qr
                result = collect_payment(row.pk, self.agent, "online")
                self.assertFalse(result["paid"])
                payload = provider.call_args.args[2]
                self.assertEqual(payload["payment_amount"], 10000)
                self.assertTrue(payload["fixed_amount"])
                self.assertEqual(payload["usage"], "single_use")
                provider.return_value = {"items": [{"id": f"pay_{row.pk}", "amount": 10000, "currency": "INR", "status": "captured"}]}
                self.assertTrue(collect_payment(row.pk, self.agent, "check")["paid"])
                self.assertTrue(collect_payment(row.pk, self.agent, "check")["paid"])
                self.assertFalse(CODRemittance.objects.filter(delivery=row).exists())
                self.assertEqual(PaymentTransaction.objects.filter(provider_payment_id=f"pay_{row.pk}").count(), 1)
                row.refresh_from_db()
                complete_delivery(row, self.agent)
                self.assertEqual(DeliveryEarning.objects.get(delivery=row).status, "payable")

    @patch("delivery.collection.provider")
    def test_mismatched_amount_does_not_mark_paid(self, provider):
        row = self.job()
        DeliveryCollection.objects.create(delivery=row, amount=100, method="online", qr_id="qr_bad")
        provider.return_value = {"items": [{"id": "pay_bad", "amount": 1, "currency": "INR", "status": "captured"}]}
        with self.assertRaises(CollectionError):
            collect_payment(row.pk, self.agent, "check")
        self.assertFalse(collection_data(row)["paid"])
        self.assertFalse(PaymentTransaction.objects.exists())

    @patch("delivery.collection.provider")
    def test_qr_timeout_persists_issuing_marker_and_blocks_duplicate(self, provider):
        row = self.job()
        provider.side_effect = CollectionError("Timeout")
        with self.assertRaises(CollectionError):
            collect_payment(row.pk, self.agent, "online")
        self.assertEqual(DeliveryCollection.objects.get(delivery=row).status, "issuing")
        with self.assertRaises(CollectionError):
            collect_payment(row.pk, self.agent, "online")
        provider.assert_called_once()

    @patch("delivery.collection.provider")
    def test_online_payment_wins_when_agent_selects_cash(self, provider):
        row = self.job()
        DeliveryCollection.objects.create(delivery=row, amount=100, method="online", qr_id="qr_cash")
        provider.return_value = {"items": [{"id": "pay_cash", "amount": 10000, "currency": "INR", "status": "captured"}]}
        result = collect_payment(row.pk, self.agent, "cash")
        self.assertEqual(result["method"], "online")
        self.assertFalse(CODRemittance.objects.exists())

    def test_partial_parcel_collection_does_not_mark_entire_order_paid(self):
        row = self.job("shop", total=300)
        row.collection_amount = 100
        row.save(update_fields=["collection_amount"])
        collect_payment(row.pk, self.agent, "cash")
        row.source_order.refresh_from_db()
        self.assertEqual(row.source_order.payment_status, "Pending")
        self.assertTrue(collection_data(row)["paid"])

    def test_prepaid_and_cancelled_deliveries_do_not_collect(self):
        row = self.job()
        row.source_order.payment_method = "online"
        row.source_order.payment_status = "Paid"
        row.source_order.save()
        with self.assertRaises(CollectionError):
            collect_payment(row.pk, self.agent, "cash")
        self.assertTrue(collection_data(row)["paid"])
        row.source_order.payment_method = "cod"
        row.source_order.status = "cancelled"
        row.source_order.save()
        with self.assertRaises(CollectionError):
            collect_payment(row.pk, self.agent, "online")

    @patch("delivery.collection.provider")
    def test_provider_rejection_allows_cash_without_creating_second_qr(self, provider):
        row = self.job()
        provider.side_effect = ProviderRejected("QR not enabled")
        with self.assertRaises(ProviderRejected):
            collect_payment(row.pk, self.agent, "online")
        self.assertTrue(collect_payment(row.pk, self.agent, "cash")["paid"])

    @patch("delivery.collection.provider")
    def test_switch_to_cash_closes_qr_and_checks_for_payments(self, provider):
        row = self.job()
        DeliveryCollection.objects.create(delivery=row, amount=100, method="online", qr_id="qr_switch")
        provider.side_effect = [
            {"items": []}, {"status": "active"}, {"status": "closed"},
            {"items": []}, {"status": "closed", "payments_count_received": 0},
        ]
        self.assertEqual(collect_payment(row.pk, self.agent, "cash")["method"], "cash")
        self.assertEqual(provider.call_args_list[2].args[:2], ("POST", "/payments/qr_codes/qr_switch/close"))

    @patch("delivery.collection.provider")
    def test_authorized_online_payment_blocks_cash_collection(self, provider):
        row = self.job()
        DeliveryCollection.objects.create(delivery=row, amount=100, method="online", qr_id="qr_auth")
        provider.return_value = {"items": [{"status": "authorized"}]}
        with self.assertRaises(CollectionError):
            collect_payment(row.pk, self.agent, "cash")
        self.assertFalse(CODRemittance.objects.exists())

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
    @patch("delivery.collection.provider")
    def test_signed_qr_webhook_verifies_capture_and_is_idempotent(self, provider):
        import hashlib
        import hmac
        import json
        from payments.services import handle_razorpay_event
        row = self.job()
        DeliveryCollection.objects.create(delivery=row, amount=100, method="online", qr_id="qr_hook")
        provider.return_value = {"items": [{"id": "pay_hook", "amount": 10000, "currency": "INR", "status": "captured"}]}
        body = json.dumps({"event": "qr_code.credited", "payload": {"qr_code": {"entity": {"id": "qr_hook"}}}}).encode()
        signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
        for _ in range(2):
            handle_razorpay_event(body, signature, "event_qr")
        self.assertTrue(collection_data(row)["paid"])
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        provider.assert_called_once()

    def test_cash_remittance_cannot_mark_partial_parcel_fully_paid(self):
        row = self.job("shop", total=300)
        row.collection_amount = 100
        row.save(update_fields=["collection_amount"])
        collect_payment(row.pk, self.agent, "cash")
        remittance = CODRemittance.objects.get(delivery=row)
        admin = User.objects.create_superuser("collection-admin", "admin@example.com", "secret")
        self.client.force_login(admin)
        self.client.post(reverse("ops_confirm_cod_remittance", args=[remittance.pk]), {"reference": "DEPOSIT"})
        row.source_order.refresh_from_db()
        self.assertEqual(row.source_order.payment_status, "Pending")

    def test_website_cash_confirmation_and_customer_payment_display(self):
        row = self.job()
        self.client.force_login(self.agent.user)
        url = reverse("delivery_payment", args=[row.pk])
        self.assertContains(self.client.get(url), "Amount due: ")
        self.client.post(url, {"action": "cash"})
        self.assertFalse(collection_data(row)["paid"])
        self.client.post(url, {"action": "cash", "confirmed": "yes"})
        self.assertContains(self.client.get(url), "Paid in cash")
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse("grocery_orders")), "in cash")

    def test_cash_blocks_seller_payout_until_remitted(self):
        from accounts.seller_payouts import submit_seller_payout, SellerPayoutError
        from groceries.models import GrocerySellerSettlement
        from django.utils import timezone
        row = self.job()
        collect_payment(row.pk, self.agent, "cash")
        settlement = GrocerySellerSettlement.objects.create(order=row.source_order, seller=self.seller,
            gross_amount=100, net_amount=100, commission_amount=0, scheduled_for=timezone.now())
        with self.assertRaisesMessage(SellerPayoutError, "remitted"):
            submit_seller_payout(settlement)

    @patch("delivery.collection.provider")
    @patch("delivery.management.commands.reconcile_delivery_qr.provider")
    def test_reconciliation_command_matches_delivery_and_amount(self, fetch, check):
        from django.core.management import call_command, CommandError
        from io import StringIO
        row = self.job()
        record = DeliveryCollection.objects.create(delivery=row, amount=100, method="online", status="issuing")
        qr = {"id": "qr_recover", "notes": {"delivery_id": str(row.pk)}, "payment_amount": 10000,
              "usage": "single_use", "fixed_amount": True, "type": "upi_qr", "image_url": "https://rzp.io/i/recover"}
        fetch.return_value = {**qr, "payment_amount": 1}
        with self.assertRaises(CommandError):
            call_command("reconcile_delivery_qr", delivery_id=row.pk, qr_id="qr_recover", stdout=StringIO())
        record.refresh_from_db()
        self.assertEqual(record.status, "issuing")
        fetch.return_value = qr
        check.return_value = {"items": []}
        call_command("reconcile_delivery_qr", delivery_id=row.pk, qr_id="qr_recover", stdout=StringIO())
        record.refresh_from_db()
        self.assertEqual(record.qr_id, "qr_recover")
        self.assertEqual(record.status, "pending")

    @patch("delivery.collection.provider")
    def test_mixed_cash_and_online_remittance_records_only_actual_cash(self, provider):
        row = self.job("shop", total=300)
        row.collection_amount = 100
        row.save(update_fields=["collection_amount"])
        second_seller = SellerProfile.objects.create(user=User.objects.create_user("second-collection-seller"), store_name="Second")
        second = LocalDelivery.objects.create(parcel_order=row.source_order, parcel_seller=second_seller,
            agent=self.agent, status="out_for_delivery", collection_amount=200)
        DeliveryCollection.objects.create(delivery=second, amount=200, qr_id="qr_mixed", method="online")
        cod = PaymentTransaction.objects.create(user=self.customer, parcel_order=row.source_order,
            channel_name="parcel", provider="cod", amount=300)
        collect_payment(row.pk, self.agent, "cash")
        provider.return_value = {"items": [{"id": "pay_mixed", "amount": 20000, "currency": "INR", "status": "captured"}]}
        collect_payment(second.pk, self.agent, "check")
        remittance = CODRemittance.objects.get(delivery=row)
        admin = User.objects.create_superuser("mixed-admin", "admin@example.com", "secret")
        self.client.force_login(admin)
        self.client.post(reverse("ops_confirm_cod_remittance", args=[remittance.pk]), {"reference": "MIXED-DEPOSIT"})
        cod.refresh_from_db()
        self.assertEqual(cod.status, "captured")
        self.assertEqual(cod.amount, Decimal("100"))
        row.source_order.refresh_from_db()
        self.assertEqual(row.source_order.payment_status, "Paid")
