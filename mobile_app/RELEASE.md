# Mobile release 1.1.0

## What ships

- Native Razorpay checkout for shop, food and grocery orders; server signature, capture, amount, currency and ownership checks; saved-order recovery after dismissal, failure or a lost callback.
- Transactional notification inbox and a push outbox for order, payment, refund and rider job events. Taps open the matching customer order or partner workspace.
- Device-specific, hashed, expiring sessions; individual revocation; push registration linked to a session; password changes revoke all mobile sessions.
- Rider background location sharing, camera proof of delivery, failed-delivery reporting, and audited dispatch reassignment before pickup. Delivery still requires the customer OTP and explicit COD collection confirmation.
- Seller cancellation/refund/dispute requests with status and resolution history; guarded administrative execution with durable refund intent.
- Customer account deletion requests, administrative access disablement, and account-data erasure after outstanding obligations are resolved.
- Read retries, finite network timeouts, render error recovery, crash-reporting integration hooks, and automated checks.

## Configure and deploy the backend

### Explicit seller segments

Apply accounts migration 0012 before running the updated backend. Registration
now requires a Merchandise, Food / restaurant, or Grocery / kirana selection;
the mobile form renders this from the server's choice schema. Existing category
descriptions remain intact. Only recognized exact legacy descriptions are
backfilled. Before launch, filter Seller profiles by blank business segment in
Django admin and explicitly assign every operating seller's segment. Unknown or
mixed descriptions, including bakery, are deliberately left for review. Segment
changes affect authorization; resolve outstanding orders before changing an
established seller's segment. Never use category text to grant workspace access.

### Authentication recovery and abuse limits

The mobile app now offers Finish email verification and signup/reset resend
controls. Deploy the backend before the updated app. No migration is needed.
Set `DJANGO_CACHE_TABLE=ziyamart_cache`, then run
`python manage.py createcachetable` against the production database before
starting web workers. All instances must share this cache. Local development
and isolated tests use process-local cache; `check --deploy` warns about it.
Do not point test settings at the production cache.

Authentication is limited per IP and normalized account; email sends share a
60-second cooldown and hourly limits. These DRF cache counters are best-effort
under concurrency, not a substitute for edge abuse protection. OTP verification
also locks the pending account and code and enforces five failed attempts.
`DJANGO_TRUSTED_PROXY_COUNT` defaults to zero: configure the real proxy chain
and forwarded-header sanitization before changing it, then verify clients have
distinct effective IPs. Test real email delivery and recovery on an installed
app before release. Unknown and disabled accounts receive generic resend text.

1. Back up the production database. Deploy the backend before the mobile release. Apply `python manage.py migrate --noinput` including mobile API migrations 0005–0009 and any later migrations.
2. Configure `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET`. Keep secrets exclusively on the server. Configure the existing `/payments/webhooks/razorpay/` endpoint for captured/failed payment, paid order and refund events.
3. Schedule `python manage.py send_mobile_notifications` every minute. The inbox is durable even when push is disabled or fails. The worker also reconciles Expo receipts after 15 minutes and disables invalid registrations. Review failed outbox entries and receipt errors in Django admin. Accepted Expo tickets are not proof that a user saw a notification. Delivery is at least once, so a worker interruption may cause a duplicate push.
4. Schedule `python manage.py cleanup_checkout_sessions` daily. It removes expired unused quotes, not unpaid orders. Pending orders remain recoverable from the customer Orders screen.
5. Mount durable private storage at `PRIVATE_MEDIA_ROOT` (default: `BASE_DIR/private_media`). Never serve this directory through public static/media routes. Back it up with restricted access. Delivery photos are streamed through the authenticated operations dashboard.
6. Existing legacy mobile tokens remain accepted for compatibility. New logins issue independent 30-day device sessions. Revoke legacy tokens during a planned forced-login rollout if required. Password reset/change also invalidates legacy tokens.

## Operations runbook

### Dispatch and evidence

Open Operations → Deliveries → a job. Review exception reasons and private proof photos. Approved agents must match the job's pincode. Dispatch may assign an offline agent deliberately; the rider must go online to claim an available job themselves. Reassigning an accepted job requires a written reason. Reassignment after pickup is refused: contact the rider and arrange a supervised handover/return. A reported failure never silently marks an order delivered or refunds it.

The rider's sharing switch starts one job's native background task. Credentials stay in SecureStore. The task uploads only the newest fresh fix; it does not retain a location history offline. It stops on logout, job completion, expiry (8 hours), revoked access or a server response saying the job is no longer active/owned. Permissions and battery management can suspend updates. Force-closing the app is not guaranteed to preserve tracking; dispatch must inspect the last GPS timestamp.

### Seller cases

Seller order cards expose cancellation, refund and dispute review requests. In Django admin → Mobile API → Seller cases, review the seller, order/item, reason and fulfilment state. Resolution edits are visible to the seller.

Approved sellers can now confirm or reject/cancel eligible orders from the mobile order detail screen. Cancellation requires a reason and uses the audited case execution service. It is item-scoped for shop orders and order-scoped for food/grocery. Stock and settlement deductions change once. Active pickup, closed orders, collected COD, initiated payouts, ownership changes and unreconciled online payments block cancellation. Refund intent is committed before the provider request; uncertain refunds remain pending for operations reconciliation. The administrative execution action remains superuser-only. Delivered goods use the existing Returns workspace and debit ledger; COD repayment requires finance reconciliation. Refund-only execution requires a cancelled item/order. Customer self-service cancellation of online orders directs customers to support so payment reconciliation happens before stock is released.

Refund intent is committed before the provider request. A timeout leaves its balance reserved. Retry the **same case** to reuse its refund idempotency key; do not create another refund. Refund webhooks update the case and notifications. A provider refund marked processing stays under review until confirmed. Disputes are resolved by the reviewer with an explanation, without an automatic money movement.

### Account deletion

Customers request deletion in Account settings and can read its status while their account is active. Submitting signs out existing mobile sessions; they can sign in to check status until access is disabled.

In Django admin → Account deletion requests, a superuser may disable access and revoke devices immediately. The separate deletion execution action erases customer account/profile/address/cart/wishlist/device data only after open orders, refunds and support requests close. It anonymizes the inactive user record and records an audit entry. Transaction and historical support records remain for operational reconciliation; the action does not claim to erase those records or backups. Partner/staff data requires a separate identity, payout and retention review and is blocked from automatic erasure. Apply the organization's documented retention policy to retained records and backups.

## Native build setup

Use Node 22.13 or later and pnpm 11.19.0. Run `pnpm install --frozen-lockfile` in `mobile_app`. Configure `EXPO_PUBLIC_API_URL` as the HTTPS backend origin and `EXPO_PUBLIC_EAS_PROJECT_ID` as the actual EAS project ID. Public variables must never contain payment secrets.

Authenticate EAS, link the existing app to its EAS project, and configure Android FCM v1/iOS APNs credentials. Verify the Android package and iOS bundle ID in app.json belong to the intended store listings before building. The repository provides development, internal preview, and production profiles; production auto-increments the remote build version. The marketing version is 1.1.0 in app.json and package.json.

```sh
pnpm exec eas build --profile development --platform android
pnpm exec eas build --profile preview --platform android
pnpm exec eas build --profile production --platform all
```

Install/use EAS CLI separately if it is not on PATH. Native Razorpay and background location require a development or release build, not Expo Go. A JavaScript export checks bundling; it does not compile or certify native payment SDK behavior.

## Crash reporting

`src/telemetry.tsx` exports `configureCrashReporter`. Bind the chosen crash SDK during application startup. Its callback receives an error name, context and fatal flag, without API payloads, tokens, addresses or payment details. The render boundary reports and offers recovery. API network failures and background location errors call the same hook. Native crash capture and source-map upload must be configured in the chosen provider's native SDK/build integration; no live provider or DSN is configured by this repository.

## Release checks

```sh
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings --noinput
cd mobile_app
pnpm typecheck
pnpm test
pnpm verify:android
```

GitHub Actions runs these checks on pushes and pull requests. The mobile unit tests exercise payment capture recovery, native callback verification, cancellation, lost confirmation, and bounded read retries without replaying writes.

Local verification completed: 151 backend tests, 11 mobile tests, TypeScript checking, migration consistency, and Android JavaScript export passed. Backend tests use SQLite; verify concurrent checkout, dispatch and refund locking against staging PostgreSQL before rollout. Background-task tests cover expiry, revoked access, denied permission and stale GPS fixes.

Before store submission, record results on physical Android and iOS devices:

- Razorpay test-mode success, failure, dismissal, app backgrounding and force-close, delayed webhook, offline verification, and return to the same unpaid order. Confirm exactly one order/stock deduction per quote and no fulfilment before capture.
- Push permission denied/allowed, foreground/background/cold-start taps, account switch, session revoke, duplicate push, and inbox pagination.
- Rider location permissions, background/locked screen, poor signal, stale timestamps, revoked assignment, photo permission/upload errors, OTP failure, and COD confirmation.
- Seller ownership rejection, repeated cancellation, refund timeout/retry with the same key, and processed-payout rejection.
- Deletion blocked by outstanding obligations, completed erasure, individual session revocation, and password-change logout.
- TalkBack/VoiceOver reading order, enlarged text, contrast, keyboard focus, touch targets, slow/offline networking, and render-boundary recovery.

Store signing, FCM/APNs delivery, real Razorpay transactions, device camera/GPS behavior and store approval require configured external accounts and device testing. Do not mark them verified based solely on unit tests or export.

## Rollback

Pause mobile rollout if crash, payment mismatch or reconciliation rates rise. Preserve payment/refund journals and webhook processing. Revert application code only to a revision compatible with the applied additive migrations; do not remove payment, case, session or notification records. Resolve reserved refunds and paid-but-unconfirmed orders before manually retrying financial actions.
