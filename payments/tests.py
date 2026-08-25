import hashlib
import hmac
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import SellerProfile
from orders.models import Order, SellerSettlement
from products.models import Category, Product, ProductColor, ProductVariant

from .models import (
    CODRemittance, PaymentTransaction, PaymentWebhookEvent, RefundTransaction,
    SellerDeliveryCharge,
)
from .pricing import build_parcel_pricing, quote_delhivery, quote_local_delivery
from .services import handle_razorpay_event, request_payment_refund


class PricingPolicyTests(TestCase):
    @override_settings(
        LOCAL_DELIVERY_BASE_FEE="30.00",
        LOCAL_DELIVERY_INCLUDED_KM="2.00",
        LOCAL_DELIVERY_PER_KM="8.00",
    )
    def test_local_delivery_is_explicitly_untaxed(self):
        quote = quote_local_delivery("28.073100", "78.750200", "28.074000", "78.751000")
        self.assertEqual(quote["carrier_amount"], Decimal("30.00"))
        self.assertEqual(quote["tax_amount"], Decimal("0.00"))
        self.assertEqual(quote["quoted_total"], Decimal("30.00"))

    @override_settings(
        DELHIVERY_API_KEY="live-test-token",
        DELHIVERY_RATE_URL="https://carrier.example/rates",
        DELHIVERY_RATE_TIMEOUT=15,
        DELHIVERY_REQUIRE_LIVE_QUOTE=True,
        DELHIVERY_HANDLING_FEE="5.00",
        DELHIVERY_GST_PERCENT="18.00",
    )
    @patch("payments.pricing.requests.get")
    def test_delhivery_quote_uses_weight_pincodes_and_carrier_tax(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"total_amount": "100.00"}]
        get.return_value = response

        quote = quote_delhivery("243638", "110001", 750, "cod")

        self.assertEqual(quote["carrier_amount"], Decimal("100.00"))
        self.assertEqual(quote["tax_amount"], Decimal("18.90"))
        self.assertEqual(quote["quoted_total"], Decimal("123.90"))
        self.assertEqual(get.call_args.kwargs["params"]["cgm"], 750)
        self.assertEqual(get.call_args.kwargs["params"]["pt"], "COD")
        self.assertEqual(get.call_args.kwargs["params"]["o_pin"], "243638")
        self.assertEqual(get.call_args.kwargs["params"]["d_pin"], "110001")

    @override_settings(
        DELHIVERY_API_KEY="",
        DELHIVERY_REQUIRE_LIVE_QUOTE=False,
        DELHIVERY_ORIGIN_PINCODE="243638",
        DELHIVERY_FALLBACK_BASE="60.00",
        DELHIVERY_FALLBACK_PER_500G="25.00",
        DELHIVERY_HANDLING_FEE="5.00",
        DELHIVERY_GST_PERCENT="18.00",
    )
    def test_direct_inventory_still_receives_a_carrier_quote(self):
        product = SimpleNamespace(
            seller=None,
            seller_id=None,
            gst_rate=Decimal("5.00"),
            package_weight_grams=500,
            package_length_cm=20,
            package_width_cm=15,
            package_height_cm=10,
        )
        variant = SimpleNamespace(seller_price=Decimal("100.00"), final_price=Decimal("110.00"))

        pricing, quotes = build_parcel_pricing(
            [{"product": product, "variant": variant, "quantity": 1}],
            {"pincode": "110001", "latitude": None, "longitude": None},
            "online",
        )

        self.assertEqual(len(quotes), 1)
        self.assertIsNone(quotes[0]["seller"])
        self.assertEqual(quotes[0]["provider"], "delhivery")
        self.assertEqual(pricing["seller_sponsored_delivery"], quotes[0]["quoted_total"])
        self.assertEqual(pricing["customer_delivery_charge"], Decimal("0.00"))


@override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
class PaymentReliabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("payment-customer")
        self.payment = PaymentTransaction.objects.create(
            user=self.user,
            channel_name="parcel",
            provider="razorpay",
            provider_order_id="order_provider_1",
            amount="100.00",
        )

    def test_payment_webhook_is_signature_checked_and_idempotent(self):
        body = json.dumps({
            "event": "payment.captured",
            "payload": {"payment": {"entity": {
                "id": "pay_provider_1",
                "order_id": "order_provider_1",
                "amount": 10000,
                "status": "captured",
            }}},
        }, separators=(",", ":")).encode()
        signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()

        first = handle_razorpay_event(body, signature, "event_1")
        second = handle_razorpay_event(body, signature, "event_1")

        self.payment.refresh_from_db()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
        self.assertEqual(self.payment.status, "captured")
        self.assertEqual(self.payment.provider_payment_id, "pay_provider_1")

    @patch("payments.services.requests.post")
    def test_refund_uses_provider_idempotency_and_updates_ledger(self, post):
        self.payment.provider_payment_id = "pay_provider_1"
        self.payment.status = "captured"
        self.payment.save(update_fields=["provider_payment_id", "status"])
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"id": "rfnd_provider_1", "status": "processed"}
        post.return_value = response

        refund = request_payment_refund(self.payment, "40.00", "Customer return")

        self.assertEqual(refund.status, "processed")
        self.assertEqual(refund.amount, Decimal("40.00"))
        self.assertEqual(RefundTransaction.objects.count(), 1)
        self.assertEqual(
            post.call_args.kwargs["headers"]["X-Refund-Idempotency"],
            str(refund.idempotency_key),
        )

    @patch("payments.services.requests.post", side_effect=requests.Timeout("provider timeout"))
    def test_failed_refund_attempt_remains_in_ledger_for_retry(self, _post):
        self.payment.provider_payment_id = "pay_provider_1"
        self.payment.status = "captured"
        self.payment.save(update_fields=["provider_payment_id", "status"])

        with self.assertRaises(requests.Timeout):
            request_payment_refund(self.payment, "25.00", "Cancelled order")

        refund = RefundTransaction.objects.get()
        self.assertEqual(refund.status, "failed")
        self.assertIn("provider timeout", refund.failure_reason)


@override_settings(
    ROOT_URLCONF="config.urls",
    SECURE_SSL_REDIRECT=False,
    BREVO_API_KEY="",
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="rzp_test_secret",
    LOCAL_DELIVERY_BASE_FEE="30.00",
    LOCAL_DELIVERY_INCLUDED_KM="2.00",
    LOCAL_DELIVERY_PER_KM="8.00",
)
class ParcelCheckoutWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            "parcel-customer", email="parcel@example.com", password="test-password",
        )
        owner = User.objects.create_user("parcel-seller")
        self.seller = SellerProfile.objects.create(
            user=owner,
            store_name="Local Parcel Seller",
            business_category="Retail",
            business_pincode="243638",
            business_latitude="28.073100",
            business_longitude="78.750200",
            business_gps_verified_at=timezone.now(),
            status="approved",
            commission_percent=Decimal("10.00"),
        )
        category = Category.objects.create(name="Parcel test", slug="parcel-test")
        product = Product.objects.create(
            category=category,
            seller=self.seller,
            name="Test Parcel Item",
            slug="test-parcel-item",
            price=Decimal("100.00"),
            gst_rate=Decimal("5.00"),
            stock=10,
        )
        color = ProductColor.objects.create(product=product, name="Black")
        self.variant = ProductVariant.objects.create(
            product=product, color=color, size="M", price=Decimal("100.00"), stock=5,
        )
        self.client.login(username="parcel-customer", password="test-password")
        self._put_item_in_cart()

    def _put_item_in_cart(self):
        session = self.client.session
        session["cart"] = {
            str(self.variant.pk): {
                "product_id": self.variant.product_id,
                "variant_id": self.variant.pk,
                "color": self.variant.color.name,
                "size": self.variant.size,
                "price": str(self.variant.final_price),
                "quantity": 1,
            }
        }
        session.save()

    def _checkout_data(self, payment_method):
        return {
            "full_name": "Parcel Customer",
            "phone": "9999999999",
            "address": "Market Road",
            "city": "Sahaswan",
            "state": "Uttar Pradesh",
            "pincode": "243638",
            "latitude": "28.074000",
            "longitude": "78.751000",
            "gps_accuracy_meters": "12",
            "gps_captured_at": timezone.now().isoformat(),
            "payment_method": payment_method,
        }

    def test_parcel_cod_creates_itemized_untaxed_local_delivery_ledger(self):
        response = self.client.post(reverse("cod_checkout"), self._checkout_data("cod"))

        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_success", args=[order.pk]))
        payment = PaymentTransaction.objects.get(parcel_order=order)
        breakdown = order.chargebreakdowns.get()
        delivery_charge = SellerDeliveryCharge.objects.get(parcel_order=order, seller=self.seller)
        self.variant.refresh_from_db()
        self.assertEqual(payment.provider, "cod")
        self.assertEqual(order.payment_status, "Pending")
        self.assertEqual(breakdown.delivery_mode, "local")
        self.assertEqual(breakdown.delivery_gst, Decimal("0.00"))
        self.assertEqual(breakdown.customer_delivery_charge, Decimal("0.00"))
        self.assertEqual(delivery_charge.tax_amount, Decimal("0.00"))
        self.assertEqual(self.variant.stock, 4)

    @patch("orders.commerce.razorpay.Client")
    def test_parcel_online_payment_verifies_and_finalizes_once(self, razorpay_client):
        razorpay_client.return_value.order.create.return_value = {"id": "order_parcel_test_1"}
        checkout_response = self.client.post(
            reverse("checkout"), self._checkout_data("online"),
        )
        self.assertEqual(checkout_response.status_code, 200)
        payment = PaymentTransaction.objects.get(provider_order_id="order_parcel_test_1")
        self.assertIsNone(payment.parcel_order_id)

        response = self.client.post(reverse("payment_success"), {
            "razorpay_order_id": "order_parcel_test_1",
            "razorpay_payment_id": "pay_parcel_test_1",
            "razorpay_signature": "test-signature",
        })

        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_success", args=[order.pk]))
        payment.refresh_from_db()
        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(payment.status, "captured")
        self.assertEqual(payment.provider_payment_id, "pay_parcel_test_1")
        self.assertEqual(order.payment_status, "Paid")
        self.assertEqual(self.variant.stock, 4)
        self.assertEqual(Order.objects.count(), 1)
        self.assertTrue(SellerSettlement.objects.filter(order=order, seller=self.seller).exists())


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False)
class CODRemittanceGateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("finance-admin", "admin@example.com", "password")
        self.customer = User.objects.create_user("cod-customer")
        self.order = Order.objects.create(
            user=self.customer,
            full_name="COD Customer",
            phone="9999999999",
            address="Market Road",
            city="Sahaswan",
            state="Uttar Pradesh",
            pincode="243638",
            total_price="200.00",
            status="Delivered",
            payment_method="cod",
            payment_status="Pending",
        )
        PaymentTransaction.objects.create(
            user=self.customer,
            channel_name="parcel",
            provider="cod",
            parcel_order=self.order,
            amount="200.00",
        )
        sellers = []
        for index in range(2):
            owner = User.objects.create_user(f"seller-{index}")
            sellers.append(SellerProfile.objects.create(user=owner, store_name=f"Seller {index}"))
        self.first = CODRemittance.objects.create(
            parcel_order=self.order,
            seller=sellers[0],
            source="delhivery",
            amount="100.00",
            status="awaiting_collection",
        )
        self.second = CODRemittance.objects.create(
            parcel_order=self.order,
            seller=sellers[1],
            source="delhivery",
            amount="100.00",
            status="awaiting_collection",
        )
        self.client.force_login(self.admin)

    def test_order_is_funded_only_after_every_seller_remittance(self):
        self.client.post(reverse("ops_confirm_cod_remittance", args=[self.first.pk]), {"reference": "DEP-1"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "Pending")

        self.client.post(reverse("ops_confirm_cod_remittance", args=[self.second.pk]), {"reference": "DEP-2"})
        self.order.refresh_from_db()
        payment = PaymentTransaction.objects.get(parcel_order=self.order)
        self.assertEqual(self.order.payment_status, "Paid")
        self.assertEqual(payment.status, "captured")


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False)
class CarrierReconciliationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            "reconciliation-admin", "reconciliation@example.com", "password",
        )
        customer = User.objects.create_user("reconciliation-customer")
        owner = User.objects.create_user("reconciliation-seller")
        self.seller = SellerProfile.objects.create(user=owner, store_name="Carrier Seller")
        self.order = Order.objects.create(
            user=customer,
            full_name="Carrier Customer",
            phone="9999999999",
            address="Market Road",
            city="Delhi",
            state="Delhi",
            pincode="110001",
            total_price="250.00",
            status="Processing",
            payment_method="online",
            payment_status="Paid",
        )
        self.charge = SellerDeliveryCharge.objects.create(
            parcel_order=self.order,
            seller=self.seller,
            provider="delhivery",
            origin_pincode="243638",
            destination_pincode="110001",
            chargeable_weight_grams=500,
            carrier_amount="100.00",
            handling_fee="5.00",
            tax_amount="18.90",
            quoted_total="123.90",
            final_total="123.90",
            status="quoted",
        )
        self.settlement = SellerSettlement.objects.create(
            seller=self.seller,
            order=self.order,
            gross_amount="200.00",
            commission_amount="20.00",
            net_amount="200.00",
            delivery_charge="123.90",
            payment_method="online",
            status="on_hold",
            scheduled_for=timezone.now(),
        )
        self.client.force_login(self.admin)

    def test_final_delhivery_bill_updates_charge_and_releases_settlement(self):
        response = self.client.post(
            reverse("ops_reconcile_delivery_charge", args=[self.charge.pk]),
            {"final_total": "119.50"},
        )

        self.assertRedirects(response, reverse("ops_payouts"))
        self.charge.refresh_from_db()
        self.settlement.refresh_from_db()
        self.assertEqual(self.charge.status, "reconciled")
        self.assertEqual(self.charge.final_total, Decimal("119.50"))
        self.assertEqual(self.settlement.delivery_charge, Decimal("119.50"))
        self.assertEqual(self.settlement.status, "scheduled")
