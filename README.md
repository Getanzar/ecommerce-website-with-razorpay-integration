# 🛒 Django E-Commerce with Razorpay Integration

A full-featured **E-Commerce web application** built with **Django** that allows users to browse products, add them to cart, checkout securely, and pay using **Razorpay (UPI, Cards, Netbanking)**.  

This project demonstrates **end-to-end web development skills** – backend, frontend, authentication, session-based cart, order management, and real-world **payment gateway integration**.

---

## ✨ Features
- 🔑 **User Authentication** – Signup, Login, Logout
- 📦 **Product Management** – Browse, search, and view product details
- 🛒 **Shopping Cart** – Add/remove products, update quantities
- 📍 **Checkout Process** – Address form, order review
- 💳 **Razorpay Payments** – Secure UPI/Credit/Debit/NetBanking support
- 📊 **Order Tracking** – Status updates (Pending → Paid)
- 🎨 **Responsive UI** – Built with Bootstrap
- 🔐 **Environment Variables** – Secure keys via `.env`

---

## 🛠️ Tech Stack
- **Backend:** Django, Python  
- **Frontend:** HTML, CSS, Bootstrap  
- **Database:** PostgreSQL in production; isolated SQLite databases for tests
- **Payment Gateway:** Razorpay API  
- **Deployment Ready:** Configurable via environment variables  

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/django-ecommerce-razorpay.git
cd django-ecommerce-razorpay
```

## Transactional email with Brevo

Signup OTPs, password-reset OTPs, order confirmations, and order-status
notifications are sent through Brevo's transactional email API. Configure
these environment variables in production:

```text
BREVO_API_KEY=your-brevo-api-key
BREVO_SENDER_NAME=ZIYAMART
BREVO_SENDER_EMAIL=orders@ziyamart.in
BREVO_API_TIMEOUT=15
```

The sender address must be verified in Brevo. Authenticate the sending domain
with the SPF and DKIM records Brevo provides before enabling production mail.

## Automatic seller payouts

Sellers see earnings under **Seller Center → Money & payouts**. Online payments
are scheduled for 9:00 AM the next day. COD is scheduled only after an admin
marks the order both `Delivered` and `Paid`.

Configure `RAZORPAYX_KEY_ID`, `RAZORPAYX_KEY_SECRET`, and
`RAZORPAYX_ACCOUNT_NUMBER`. In Django admin, enter each verified seller's
`razorpay_fund_account_id` and enable `payouts_enabled`.

Run migrations, then schedule this command every morning:

```bash
python manage.py migrate
python manage.py process_seller_payouts
```

Use `python manage.py process_seller_payouts --dry-run` to reconcile earnings
and show due settlements without transferring funds.

`RAZORPAYX_ACCOUNT_NUMBER` is the platform payout account number displayed in
RazorpayX under account details; it is not a seller bank-account number.
Completed, processed returns create seller debits automatically. Debits offset
the next payout and any shortfall remains visible to the seller with an in-app
notification requesting the outstanding amount.

Set `RAZORPAYX_WEBHOOK_SECRET` and register this live webhook URL in Razorpay:

```text
https://YOUR-DOMAIN/orders/webhooks/razorpayx/
```

Subscribe to payout status events. Also schedule
`python manage.py process_seller_payouts` at least every morning; running it
more frequently safely reconciles missed orders and payout statuses.

For general merchandise, seller-entered prices are their earnings before
returns. The customer-facing price adds the seller commission percentage on
top. Product edits return to moderation, inventory updates are immediate, and
each seller can fulfil only their own order items.

## Payments, delivery charges, and tax ledgers

Parcel, food, and grocery checkouts persist an immutable breakdown for seller
merchandise, platform fee, merchandise GST, platform-fee GST, delivery, and
seller-sponsored delivery. Local delivery tax is always zero. Food and grocery
orders are local-only. Parcel orders use a GPS-priced local rider when the
seller and customer pincodes match; otherwise they use a Delhivery rate quote.
Both local and Delhivery delivery charges are deducted from the responsible
seller settlement rather than added to the customer payable total.

Delivery agents see gross earning, the 10% platform fee, and their net earning
before accepting an order. RazorpayX sends the net amount to the verified agent
fund account. COD earnings remain pending until the corresponding rider or
carrier remittance is confirmed in the admin payout workspace.

Register the customer-payment webhook at:

```text
https://YOUR-DOMAIN/payments/webhooks/razorpay/
```

Set `RAZORPAY_WEBHOOK_SECRET` and subscribe to payment captured, payment
failed, order paid, and refund events. Webhook event IDs, provider order IDs,
payout keys, and refund keys are idempotent.

For carrier operations, schedule this command every 15–30 minutes:

```bash
python manage.py refresh_delhivery_shipments
```

Use **Admin dashboard → Payouts & settlements** to confirm COD remittances and
enter the final Delhivery invoice amount. A Delhivery-funded seller settlement
stays on hold until its carrier charge is reconciled.

## Storefront launch safeguards

Customer-facing catalog, API, wishlist, cart, and checkout paths expose only
active, admin-approved products from approved sellers. Availability comes from
active variant stock rather than the legacy product stock field. Product and
cart prices are displayed inclusive of merchandise GST and platform-fee GST;
seller-sponsored delivery leaves the customer delivery charge at zero.

Parcel returns are accepted for seven days after the recorded delivery time.
Configure the window with `RETURN_WINDOW_DAYS`. Before every deployment run:

```bash
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py test --settings=config.test_settings
```

Production defaults enable a one-year HSTS policy with subdomains and preload.
Confirm every subdomain is HTTPS before keeping `SECURE_HSTS_INCLUDE_SUBDOMAINS`
and `SECURE_HSTS_PRELOAD` enabled.
