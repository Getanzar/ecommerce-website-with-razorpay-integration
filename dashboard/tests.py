from django.utils import timezone as django_timezone
from unittest.mock import patch
from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import SellerProfile
from delivery.models import DeliveryAgentProfile, LocalDelivery
from groceries.models import GroceryOrder, GroceryServiceArea, GroceryStore
from orders.models import Order
from products.models import Category

from .models import AdminAuditLog


@override_settings(ROOT_URLCONF="config.urls", SECURE_SSL_REDIRECT=False)
class OperationsDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("operator", "operator@example.com", "test-password")
        self.customer = User.objects.create_user("real-customer", "customer@example.com", "test-password")

    def test_dashboard_requires_operations_access(self):
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 302)
        ordinary = User.objects.create_user("ordinary", password="test-password")
        self.client.login(username="ordinary", password="test-password")
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)
        self.client.login(username="operator", password="test-password")
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 200)

    def test_staff_can_be_granted_operations_permission(self):
        staff = User.objects.create_user("staff", password="test-password", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="access_operations_dashboard"))
        self.client.login(username="staff", password="test-password")
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ops_delivery_agents")).status_code, 200)
        self.assertEqual(self.client.get(reverse("sellers_management")).status_code, 200)

    def test_category_creation_is_protected_and_delete_requires_post(self):
        self.assertEqual(self.client.post(reverse("add_category"), {"name": "Unsafe"}).status_code, 302)
        self.assertFalse(Category.objects.filter(name="Unsafe").exists())
        self.client.login(username="operator", password="test-password")
        self.client.post(reverse("add_category"), {"name": "Safe category"})
        category = Category.objects.get(name="Safe category")
        self.assertEqual(self.client.get(reverse("delete_category", args=[category.pk])).status_code, 405)
        self.client.post(reverse("delete_category", args=[category.pk]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_order_updates_require_post_and_enforce_the_workflow(self):
        order = Order.objects.create(
            user=self.customer,
            full_name="Customer",
            phone="8888888888",
            address="Road",
            city="Town",
            state="State",
            pincode="243638",
            total_price=100,
        )
        self.client.login(username="operator", password="test-password")
        url = reverse("update_order_status", args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url, {"status": "Delivered", "payment_status": "Paid"})
        order.refresh_from_db()
        self.assertEqual(order.status, "Pending")
        self.assertEqual(order.payment_status, "Pending")
        self.assertFalse(AdminAuditLog.objects.filter(action="order.update", entity_id=str(order.pk)).exists())

    def test_customer_workspace_excludes_sellers_and_agents(self):
        seller_user = User.objects.create_user("seller-user")
        SellerProfile.objects.create(user=seller_user, store_name="Seller Store")
        agent_user = User.objects.create_user("agent-user")
        DeliveryAgentProfile.objects.create(
            user=agent_user, full_name="Agent", phone="9999999999", address="Road", city="Town",
            state="State", pincode="243638", vehicle_type="bicycle", aadhaar_last4="1234",
        )
        self.client.login(username="operator", password="test-password")
        response = self.client.get(reverse("ops_customers"))
        self.assertContains(response, "real-customer")
        self.assertNotContains(response, "seller-user")
        self.assertNotContains(response, "agent-user")

    def test_customer_block_requires_reason_and_is_audited(self):
        self.client.login(username="operator", password="test-password")
        url = reverse("ops_update_customer", args=[self.customer.pk])
        self.client.post(url, {"action": "block"})
        self.customer.refresh_from_db(); self.assertTrue(self.customer.is_active)
        self.client.post(url, {"action": "block", "reason": "Confirmed abuse"})
        self.customer.refresh_from_db(); self.assertFalse(self.customer.is_active)
        self.assertTrue(AdminAuditLog.objects.filter(action="customer.block", entity_id=str(self.customer.pk)).exists())

    def test_assignment_enforces_matching_pincode_and_writes_audit(self):
        owner = User.objects.create_user("owner")
        seller = SellerProfile.objects.create(user=owner, store_name="Local Store", status="approved")
        area = GroceryServiceArea.objects.create(pincode="243638", city="Town")
        store = GroceryStore.objects.create(seller=seller, name="Local Store", address="Market", pincode="243638", phone="9999999999")
        store.service_areas.add(area)
        order = GroceryOrder.objects.create(
            user=self.customer, store=store, full_name="Customer", phone="8888888888", address="Road",
            city="Town", state="State", pincode="243638", subtotal=100, total=120, delivery_fee=20,
            delivery_mode="local", status="ready",
        )
        job = LocalDelivery.objects.create(
            grocery_order=order, pincode="243638", pickup_name="Local Store", pickup_address="Market",
            customer_name="Customer", customer_phone="8888888888", delivery_address="Road", delivery_fee=20, agent_earning=20,
        )
        agent_user = User.objects.create_user("matching-agent")
        agent = DeliveryAgentProfile.objects.create(
            user=agent_user, full_name="Matching Agent", phone="7777777777", address="Road", city="Town",
            state="State", pincode="243638", vehicle_type="bicycle", aadhaar_last4="1234", status="approved",
        )
        self.client.login(username="operator", password="test-password")
        self.client.post(reverse("ops_assign_delivery", args=[job.pk]), {"agent_id": agent.pk})
        job.refresh_from_db(); self.assertEqual(job.agent, agent); self.assertEqual(job.status, "assigned")
        self.assertTrue(AdminAuditLog.objects.filter(action="delivery.assign", entity_id=str(job.pk)).exists())
        self.assertEqual(self.client.get(reverse("ops_delivery_detail", args=[job.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("ops_order_detail", args=["grocery", order.pk])).status_code, 200)
    def test_primary_operations_pages_render(self):
        self.client.login(
            username="operator",
            password="test-password",
        )

        names = (
            "ops_search",
            "ops_delivery_agents",
            "ops_customers",
            "ops_orders",
            "ops_deliveries",
            "ops_payouts",
            "ops_zones",
            "ops_audit",
            "sellers_management",
            "products_management",
            "inventory_management",
            "categories_management",
            "subcategories_management",
            "catalog_requests_management",
            "reviews_management",
            "returns_management",
            "support_management",
            "analytics_dashboard",
            "orders_management",
        )

        for name in names:
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(reverse(name)).status_code,
                    200,
                )

    @patch("accounts.seller_payouts.requests.post")
    @override_settings(
        RAZORPAYX_KEY_ID="rzp_test_x_key",
        RAZORPAYX_KEY_SECRET="rzp_test_x_secret",
        RAZORPAYX_ACCOUNT_NUMBER="2323230000000000",
        SELLER_PAYOUT_MODE="IMPS",
    )
    def test_operator_can_submit_shop_seller_settlement_payout(self, post):
        from decimal import Decimal

        from orders.models import SellerSettlement

        seller_user = User.objects.create_user(
            username="settlement-seller",
            email="settlement-seller@example.com",
        )

        seller = SellerProfile.objects.create(
            user=seller_user,
            store_name="Settlement Test Store",
            legal_business_name="Settlement Test Store",
            business_segment="shop",
            status="approved",
            payouts_enabled=True,
            razorpay_fund_account_id="fa_test_seller_123",
        )

        order = Order.objects.create(
            user=self.customer,
            full_name="Settlement Customer",
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
            status="scheduled",
            scheduled_for=django_timezone.now(),
        )

        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {
            "id": "pout_shop_test_123",
            "status": "queued",
        }

        self.client.login(
            username="operator",
            password="test-password",
        )

        response = self.client.post(
            reverse(
                "ops_submit_seller_payout",
                args=["shop", settlement.pk],
            )
        )

        self.assertEqual(response.status_code, 302)

        settlement.refresh_from_db()

        self.assertEqual(settlement.status, "processing")
        self.assertEqual(
            settlement.provider_payout_id,
            "pout_shop_test_123",
        )
        self.assertEqual(settlement.failure_reason, "")
        self.assertIsNone(settlement.processed_at)

        post.assert_called_once()

        _, kwargs = post.call_args

        self.assertEqual(kwargs["json"]["amount"], 90000)
        self.assertEqual(
            kwargs["json"]["fund_account_id"],
            "fa_test_seller_123",
        )
        self.assertEqual(
            kwargs["headers"]["X-Payout-Idempotency"],
            settlement.payout_reference_key,
        )