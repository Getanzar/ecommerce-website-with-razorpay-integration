# Order and delivery verification — 7 October 2026

## Saved changes

- Admin dashboard links to **Seller areas & riders** at `/dashboard/operations/coverage/`. Search seller names, pickup addresses and pincodes. View approved, online and pending riders, disabled zones, GPS setup and saved courier pickup names.
- Parcel pricing, used by website and app, selects local delivery for matching seller/buyer pincodes only when active accounts with approved riders cover the pincode and its delivery zone is not disabled. Offline approved riders retain coverage; jobs wait for a rider to go online and claim them. Without coverage, quote Delhivery. A failed live courier quote blocks checkout when `DELHIVERY_REQUIRE_LIVE_QUOTE=True`.
- Local delivery remains a job offered to eligible riders, who claim it; it does not forcibly assign an individual rider. The admin can assign a rider through Local deliveries.
- Mobile paid/COD parcel checkout now schedules Delhivery manifestation after database commit. The scheduled `book_delhivery_shipments` command remains the recovery path for unattempted packages. Existing AWBs prevent repeat manifestation; ambiguous provider failures require reconciliation.
- Website merchandise sellers see saved new-order alerts in Seller Center. Existing app inbox/push alerts are created once per seller after payment is captured or for COD. Food and grocery retain their preparation/packing then ready workflow and separate service-area configuration.
- A same-area match across different pincodes is not currently defined; those parcel orders use courier shipping.

## Evidence

- Public deployed `/api/v1/categories/` returned HTTP 200. This confirms API reachability, not payment or shipment acceptance.
- App production configuration points to `https://ziyamart.in/api/v1`; its production URL check passed.
- All 231 backend tests and 33 mobile tests passed. Backend tests use isolated SQLite and mocked providers; they do not transfer real money or book real deliveries.
- No new migrations required by these changes. Existing uncommitted migrations from earlier work must still be included in the deployment.

## Remaining production verification

These changes are local and have not been deployed during this task. No Render settings or secrets were changed. Deploy the reviewed working changes, run migrations and check production configuration with `python manage.py check_commerce_launch`.

Run `python manage.py send_mobile_notifications` every minute. Sellers/riders need a physical installed app build with notification permission, registered device tokens and configured Expo/FCM/APNs credentials for push messages; stored inbox alerts alone do not prove that a phone notification was delivered. Inspect the notification outbox and push receipts through the main dashboard.

Run `python manage.py book_delhivery_shipments` regularly and `python manage.py refresh_delhivery_shipments` for tracking. Confirm Delhivery credentials, live quotes and each seller's actual registered pickup name. An AWB/manifest does not by itself request physical pickup or prove collection.

Verify the Razorpay live webhook at `/payments/webhooks/razorpay/` and its secret. On both deployed website and installed app, place a small paid order, confirm captured payment, one seller alert, correct local job or courier AWB, and one stock deduction. Test browser/app closure after payment and duplicate callbacks. Run a real local rider claim, pickup and delivery OTP flow before promising local delivery in a pincode.
