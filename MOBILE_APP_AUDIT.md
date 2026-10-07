# Mobile app audit — 7 October 2026

Result: automated checks pass; installed-app and live-provider acceptance remain unverified.

The production app configuration uses `https://ziyamart.in/api/v1`, the Django backend serving the website. Accounts, seller profiles, catalog, stock, orders and delivery records are shared. Website sessions and app device tokens authenticate separately. API cart behavior is tested; this audit does not claim every anonymous browser cart synchronizes to every phone.

## Reviewed flows and evidence

| Area | Automated checks / source review | Live or physical-device check remaining |
| --- | --- | --- |
| Signup | Inactive signup, OTP activation/replay/expiry, resend cooldown, failed-email rollback, input/password validation | Receive real Brevo OTP and complete signup |
| Login and sessions | Token-protected profile, login limits, password reset/session revocation, saved-session handling, stale 401 isolation | Login, reopen app, switch accounts, sign out on installed build |
| Seller Center | Existing seller roles, approval and segment checks; owned products/orders/payouts; product photos, colours and variants; moderation; order confirm/cancel and refund safeguards | Assign correct approved segment; create a listing on phone and confirm it appears on website after approval |
| Catalog, cart and addresses | Pagination/filtering, stock variants, quantity validation, duplicate cart consolidation, address ownership/defaults | Browse actual launch products and add correct colour/size |
| Checkout | Fresh GPS quote, address/quote binding, expiry/requote, COD limits, order idempotency, stock reservation | Confirm actual location permissions and totals on device |
| Razorpay | Signature, captured state, amount/currency/ownership verification, native callback recovery, failed/dismissed/lost-confirmation behavior | One small real payment, app interruption, webhook recovery and refund |
| Orders and support | History, customer-only records, invoices, review eligibility, return/support workflows | Inspect a real web order from app and an app order from website |
| Notifications | Seller alerts once, durable inbox/outbox, disabled preferences, revoked devices, invalid-token receipts | Phone permission, FCM/APNs credentials, actual received alert and tap navigation |
| Local delivery | Same-pincode coverage, paid/COD dispatch, claim ownership, OTP/cash completion, earnings | Online rider, pickup, GPS tracking and emailed OTP delivery |
| Courier delivery | Per-seller charge records, paid/COD eligibility, post-commit booking, existing-AWB guards | Actual Delhivery AWB, label, pickup and tracking |
| Rider tracking | Denied permissions, stale fixes, expired/revoked scoped credentials | Locked-screen/background behavior and physical delivery |

## Fix during this audit

The checkout screen previously awaited cart refresh before opening Razorpay. A temporary cart-read failure could prevent payment for an already-created order. Payment now runs first; refresh failures do not replace a payment success or recovery message. COD does not invoke Razorpay. The older merchandise cart screen also keeps its active checkout mounted when the cart becomes empty.

Three regression tests cover payment-before-refresh, retaining payment recovery instructions when refresh also fails, and COD without Razorpay.

## Validation

- 237 backend tests passed with isolated SQLite and mocked providers.
- 36 mobile tests passed; production URL guard and TypeScript check passed.
- Android and iOS JavaScript exports passed. An export is not a signed native build or device test.
- Deployed categories and products endpoints returned HTTP 200; anonymous partner roles/cart returned HTTP 401.
- No real account, product, order, payment, shipment or payout was created on production for this audit.

## Install and acceptance

Pushes to GitHub update source; existing installed apps need a new development/release build containing these changes. Use the existing EAS production profile for release. Expo Go does not include the required native Razorpay module.

Run the real-device sequence in `MANUAL_LAUNCH_CHECKS.md`: signup/OTP, login/reopen/signout, seller workspace/listing, one paid website order visible in app, one paid app order visible on website, seller push alert, same-pincode rider delivery, courier AWB, then payment failure/recovery and refund. Record the build version and each order/payment/AWB reference. Backend tests on SQLite do not validate concurrent production PostgreSQL locking.
