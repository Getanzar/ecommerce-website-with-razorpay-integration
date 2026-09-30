# Mobile development status

## Seller and rider workspaces

Open **Account → Seller Center** or **Account → Rider workspace** after signing in.
The same authenticated account can shop and apply for partner roles. The server
controls approval; a client cannot choose its own privileges.

Implemented:

- Native seller and rider application forms with pending/blocked status screens.
- Native bank setup using the existing provider integration. Account numbers are
  not returned to clients or persisted in full. New bank details disable payouts
  until marketplace verification. Tests mock provider calls.
- Seller merchandise, food, and grocery order lists, paginated and scoped to the
  current seller. Merchandise totals show only that seller's items.
- Forward fulfilment transitions with payment and state checks; local-delivery
  completion remains owned by the rider workflow.
- Stock changes and listing/menu visibility controls. Unapproved merchandise
  cannot be published.
- Merchandise creation/editing, store configuration, food/grocery creation and
  editing, and variant creation/editing. Merchandise changes require moderation.
- Seller settlement history and return balance, including payout failure details.
- Rider online/offline controls, pincode-scoped available jobs, active jobs,
  history, and earning records.
- Claim conflict handling, stage updates, customer call/navigation, explicit COD
  collection confirmation, and customer OTP completion. Duplicate completion
  does not create another earning.
- Opt-in native background location sharing, scoped to one active job, with
  explicit stop, expiry and revoked-assignment handling. Available and historical jobs hide customer
  contact and delivery-address details.
- Loading, empty/error/retry states, pull-to-refresh, and pagination.

Backend routes live under `/api/v1/partners/`. Applications and payout setup use
separate endpoints. Role checks are enforced on every protected endpoint.

## Validation

- `npm run typecheck`
- `npm run verify:android` checks the Android JavaScript/assets export; it does
  not create a signed APK or prove behavior on a real device.
- `python manage.py test mobile_api --settings=config.test_settings`
  includes customer API regressions and partner isolation/lifecycle tests.

The local test configuration uses SQLite. Before release, exercise concurrent
stock changes, claims, and completion against PostgreSQL, then test real-device
GPS permissions, image uploads, navigation, OTP delivery, and bank provisioning
using staging credentials. Deploy the backend with the app; an older production
API will not expose these workspaces.

## Release 1.1.0 operations

Native Razorpay, saved-payment recovery, notification inbox and receipt processing,
device sessions, seller exception review/execution, private delivery evidence,
dispatch reassignment and customer account-deletion execution are implemented.
Crash-reporting hooks, bounded read retries, mobile tests, EAS profiles and CI are
included. See [RELEASE.md](RELEASE.md) for deployment and operational instructions.

Production signing, payment/push credentials, crash-provider configuration,
physical Android/iOS accessibility and GPS checks, store submission, and published
retention policies remain deployment tasks. Partner/staff deletion requires a
separate payout/identity review. Delivered-item refunds use the existing return
ledger; automatic money movement is refused when payout reconciliation is needed.

Seller analytics, bulk catalog tools and broader exchange workflows are separate
product backlog items.

Existing customer functionality and unrelated local changes have been retained.
