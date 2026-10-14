Grocery pack sizes
==================
Sellers add a product once. The first pack uses the existing size, price, MRP and stock fields; additional pack sizes have their own prices and stock. Stock counts packs. Customers choose size and number of packs on category/store cards and in the mobile product detail screen.

Cart rows, quotes, orders and cancellation restore the selected pack. Order size and price are immutable snapshots. Removing an additional pack deactivates it, preserving order history. Existing products and database carts are backfilled with their original size by groceries migration 0008. Existing session carts keep working.

Deployment: apply migrations before serving updated code (python manage.py migrate). This includes the earlier small-seller migration. No production database was changed during development.

Mobile seller inventory lists each pack and supports stock updates by variant_id; its existing product form edits the first pack. Additional pack creation/editing is available in the website seller product editor.
