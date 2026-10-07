# Manual checks after GitHub deployment

Use a low-priced real product and separate buyer, seller and rider accounts. Record each order ID, payment ID and shipment AWB. A successful payment is real money; refunds must be verified in Razorpay.

## 1. Confirm Render deployed the pushed commit

Open https://dashboard.render.com, select the website service, then Events. Match the deployed commit to GitHub main and wait for Live. If auto-deploy is off, select Manual Deploy → Deploy latest commit. Read logs for migration, startup or database errors. GitHub Actions checks should also pass.

The repository Procfile runs migrations before Gunicorn, but verify Render's actual configured commands. In the service Shell, if available, run:

```sh
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py check_commerce_launch
python manage.py check --deploy
```

Confirm products migrations 0023 and 0024 are applied. Resolve reported production configuration issues; local tests do not verify Render settings. Back up the production database before applying deployment migrations.

## 2. Check production settings

In Render → service → Environment, confirm live customer Razorpay key ID/secret, a webhook secret, Brevo credentials and verified sender, Delhivery credentials and the exact registered platform pickup name. Use `DEBUG=False`, HTTPS configuration appropriate for Render, and `DELHIVERY_REQUIRE_LIVE_QUOTE=True`. Each seller shipping from their own location needs their own registered `delhivery_pickup_name` in Django admin → Seller profiles.

RazorpayX payout credentials are separate from customer payment credentials. Enable seller/rider payouts only after recipient verification and a small successful payout.

## 3. Verify Razorpay webhook

In Razorpay Live mode → Webhooks, configure:

`https://ziyamart.in/payments/webhooks/razorpay/`

Use the same secret as Render's `RAZORPAY_WEBHOOK_SECRET`. Subscribe to `payment.captured`, `payment.failed`, `order.paid`, `refund.processed` and `refund.failed`. Inspect recent webhook delivery responses after the test purchases. Successful events must receive a 2xx response. Customer payment keys alone do not configure webhooks.

## 4. Confirm scheduled jobs actually run

Use Render Cron Jobs or your existing scheduler with the same production database and environment settings:

| Command | Suggested frequency | What to check |
| --- | --- | --- |
| `python manage.py send_mobile_notifications` | Every minute | Recent successful runs; outbox and push receipts |
| `python manage.py book_delhivery_shipments` | Every 5 minutes | Paid/COD packages get an AWB; unresolved errors reviewed |
| `python manage.py refresh_delhivery_shipments` | Every 15–30 minutes | Courier tracking updates |
| `python manage.py cleanup_checkout_sessions` | Daily | Successful cleanup runs |
| `python manage.py process_seller_payouts` | At least each morning | Only after verified live payout setup |

Render cron schedules use UTC. 9:00 AM India time is 03:30 UTC. Do not assume a command runs periodically because it exists in the repository. A one-off run of `send_mobile_notifications` from Shell can help isolate scheduling failures.

## 5. Check seller products on website and app

Approve the seller, select the correct business segment, save their pickup address/pincode and GPS, then approve a product with photos, price and a stocked variant. Kids' Wear needs gender and age group. Confirm the same product and stock are visible on the website and installed app. Add the correct size/colour to the cart on each.

## 6. Check local coverage

Open main dashboard → Seller areas & riders. Search the seller pincode. Approve a rider with an active account in that pincode and have them go online. Ensure the delivery zone is not disabled. Confirm the seller's address, GPS and approved/online rider counts.

Matching seller/buyer pincodes with approved rider coverage select local parcel delivery. Offline approved riders retain coverage but jobs wait for someone to go online. Areas without approved rider coverage use Delhivery; a different pincode also uses Delhivery. Same-area routing across different pincodes is not defined.

## 7. Place a paid website order

Sign in as buyer, add the stocked product, select a delivery address and capture GPS, then pay through Razorpay. Verify one order in My orders and admin, Paid status, correct total and one stock deduction. Check the payment is Captured in Razorpay. Sign in as seller and verify the website order alert, order items and seller app inbox. Also try closing checkout after payment; the webhook must still complete/recover the order.

## 8. Check real phone notifications

Install a development/production app build on a physical phone, sign in as seller/rider and allow notifications. Expo Go does not provide the required remote push setup. Place an order and check inbox, phone notification and notification tap navigation. In dashboard → Notification outbox, verify the seller/rider entry; inspect Push delivery receipts for provider errors. A saved inbox entry or accepted push ticket alone is not proof the phone displayed the alert.

## 9. Complete a local delivery

For a same-pincode local order, confirm Local deliveries shows one job for that seller. Rider claims it, picks it up, marks out for delivery and completes with the buyer's emailed OTP. Verify buyer tracking, final Delivered state and rider earnings. For food/grocery, the seller must mark prepared/packed and then Ready before a rider job appears. For COD, verify the correct collection amount and admin remittance confirmation.

## 10. Verify a Delhivery parcel

Use a serviceable destination outside the seller pincode, or a same-pincode area without local coverage. Confirm the package uses Delhivery and receives an actual AWB. Verify it in Delhivery's portal, obtain the label and arrange pickup through the carrier workflow. Confirm physical pickup and tracking updates. An AWB is not proof pickup has been scheduled. If status is manifestation_failed/pending, reconcile using the unique order-seller reference before retrying.

## 11. Verify the updated installed app

GitHub push deploys source, not a replacement phone app. Build/distribute the app through the existing EAS release process using the production profile pointing at `https://ziyamart.in/api/v1`. Install the new build. Repeat the paid checkout, seller alert and delivery tests on it. Confirm reopening the app restores login and order history.

## 12. Check failure, cancellation, refund and payout

Dismiss a payment attempt: it must not appear Paid or dispatch a delivery. Retry/recover and confirm there is one payment/order and no duplicate stock deduction or shipment. Use the supported cancellation/refund process and confirm the processed refund in Razorpay and both order screens. Verify transactional email delivery. Finally run one small seller/rider payout only after recipient and RazorpayX setup, and confirm credited funds and dashboard status.

Only describe payment, push or delivery as verified after its real provider/device check passes.

References: https://render.com/docs/deploys, https://render.com/docs/cronjobs, https://razorpay.com/docs/webhooks/
