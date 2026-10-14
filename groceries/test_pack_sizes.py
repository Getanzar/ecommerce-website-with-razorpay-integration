from decimal import Decimal
from django.urls import reverse
from . import tests as fixtures
from .models import GroceryProductOption, GroceryOrder, GroceryCartItem
from .options import lock_grocery_rows, reserve_order_items, restore_order_stock, GroceryInventoryError
from .forms import GroceryOptionFormSet

from django.test import TestCase

class GroceryPackTests(TestCase):
    setUp = fixtures.GroceryMarketplaceTests.setUp
    def pack(self):
        return GroceryProductOption.objects.create(product=self.product, unit="1 kg", price=50, mrp=70, stock=3)

    def test_same_product_different_packs_have_independent_cart_lines(self):
        pack = self.pack()
        self.client.get(reverse("grocery_home"), {"pincode": "243638"})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]), {"quantity": 2})
        self.client.post(reverse("grocery_cart_add", args=[self.product.pk]), {"quantity": 3, "option_id": pack.pk})
        response = self.client.get(reverse("grocery_cart"))
        rows = response.context["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["option"].unit for row in rows}, {"5 kg", "1 kg"})
        self.client.post(reverse("grocery_cart_remove", args=[self.product.pk]), {"option_id": pack.pk})
        self.assertEqual(len(self.client.get(reverse("grocery_cart")).context["rows"]), 1)

    def test_reservation_and_cancel_restore_exact_pack_and_keep_snapshot(self):
        pack = self.pack()
        order = GroceryOrder.objects.create(user=self.customer, store=self.store, subtotal=110, total=130, delivery_mode="local")
        rows = lock_grocery_rows([{"product": self.product, "option": pack, "quantity": 2}])
        reserve_order_items(order, rows)
        pack.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(pack.stock, 1)
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(order.items.get().unit, "1 kg")
        pack.unit = "1000 g"; pack.price = 60; pack.save()
        restore_order_stock(order)
        pack.refresh_from_db()
        self.assertEqual(pack.stock, 3)
        self.assertEqual(order.items.get().unit, "1 kg")
        self.assertEqual(order.items.get().unit_price, Decimal("55.00"))

    def test_sold_out_selected_size_is_rejected_even_when_other_size_available(self):
        pack = self.pack(); pack.stock = 0; pack.save()
        with self.assertRaises(GroceryInventoryError):
            lock_grocery_rows([{"product": self.product, "option": pack, "quantity": 1}])

    def test_seller_formset_saves_and_soft_removes_size(self):
        data = {"sizes-TOTAL_FORMS": "1", "sizes-INITIAL_FORMS": "0", "sizes-0-unit": "1 kg", "sizes-0-price": "50", "sizes-0-mrp": "70", "sizes-0-stock": "3", "sizes-0-is_active": "on"}
        formset = GroceryOptionFormSet(data, instance=self.product, prefix="sizes", queryset=self.product.options.filter(is_default=False))
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        pack = self.product.options.get(is_default=False)
        data.update({"sizes-INITIAL_FORMS": "1", "sizes-0-id": str(pack.pk), "sizes-0-DELETE": "on"})
        formset = GroceryOptionFormSet(data, instance=self.product, prefix="sizes", queryset=self.product.options.filter(is_default=False))
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save(); pack.refresh_from_db()
        self.assertFalse(pack.is_active)

    def test_failed_browser_payment_restores_alternate_pack_once(self):
        from payments.services import create_payment_transaction, _sync_order_payment
        pack = self.pack()
        order = GroceryOrder.objects.create(user=self.customer, store=self.store, subtotal=110, total=130, delivery_mode="local", payment_method="online")
        reserve_order_items(order, lock_grocery_rows([{"product": self.product, "option": pack, "quantity": 2}]))
        payment = create_payment_transaction(order, "order_pack_failure")
        _sync_order_payment(payment, False)
        _sync_order_payment(payment, False)
        pack.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(pack.stock, 3)
        self.assertEqual(self.product.stock, 10)

    def test_migration_preserves_existing_unit_and_database_cart(self):
        import importlib
        from types import SimpleNamespace
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        self.product.options.all().delete()
        historical = MigrationExecutor(connection).loader.project_state([("groceries", "0008_grocery_product_pack_sizes")]).apps
        old_cart = historical.get_model("groceries", "GroceryCartItem").objects.create(user_id=self.customer.pk, product_id=self.product.pk, quantity=2)
        migration = importlib.import_module("groceries.migrations.0008_grocery_product_pack_sizes")
        migration.preserve_existing_units(historical, SimpleNamespace(connection=connection))
        default = self.product.default_option
        self.assertEqual((default.unit, default.price, default.stock), ("5 kg", Decimal("250.00"), 10))
        self.assertEqual(GroceryCartItem.objects.get(pk=old_cart.pk).option_id, default.pk)

    def test_seller_creates_product_and_sizes_in_one_submission(self):
        self.client.force_login(self.owner)
        payload = {"category": self.product.category_id, "name": "Rice packs", "unit": "500 g", "price": "30", "mrp": "40", "stock": "4", "gst_rate": "0", "is_active": "on", "sizes-TOTAL_FORMS": "1", "sizes-INITIAL_FORMS": "0", "sizes-0-unit": "1 kg", "sizes-0-price": "50", "sizes-0-mrp": "70", "sizes-0-stock": "3", "sizes-0-is_active": "on"}
        response = self.client.post(reverse("grocery_seller_add_product"), payload)
        self.assertEqual(response.status_code, 302)
        product = self.store.products.get(name="Rice packs")
        self.assertEqual(set(product.options.values_list("unit", "stock")), {("500 g", 4), ("1 kg", 3)})
