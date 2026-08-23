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
- **Database:** SQLite (default) / PostgreSQL (production-ready)  
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
