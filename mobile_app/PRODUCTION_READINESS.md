# Production readiness — 20 September 2026

Status: local implementation and automated checks passed; not yet verified for production release. External production accounts, credentials, workers and store configuration were not audited during this review.

## Completed in this update

- Seller Center shows only the segment resolved from the saved seller registration. Backend authorization blocks other segments and other sellers' records.
- Orders appear as compact, tappable rows. Merchandise orders are grouped once per order, including only the current seller's items. Pagination remains available.
- Order details show customer/address, payment state, date, items, seller merchandise total, status, and tracking information.
- Sellers can confirm eligible orders and advance fulfilment. Merchandise actions are per item; food and grocery actions are per order.
- Sellers can reject/cancel eligible orders with a reason. The existing audited cancellation service restores eligible stock, cancels applicable delivery jobs, adjusts settlements and reserves online refunds before contacting the provider.
- Repeat cancellation does not restore stock or reserve a refund twice. Provider uncertainty is reported as pending, not as a failed cancellation or a completed refund.
- Picked-up/closed orders, advanced fulfilment, initiated payouts, collected COD and unreconciled online payments require the existing operations/finance workflow.

Validation this session: 166 backend tests on isolated SQLite, 15 mobile tests, TypeScript checking, Android and iOS JavaScript/asset exports passed. Provider requests in tests were mocked. This is not a native build or physical-device verification.

## Required before release

1. **Version control and deployment source.** The root `.gitignore` excludes both `mobile_app/` and `mobile_api/`; neither directory has a separate `.git` directory in this workspace. Establish a tracked source/deployment path for these changes. Verify a clean checkout contains the mobile API, app, migrations and tests and that CI runs successfully from it. Existing product model/migration changes also need review and inclusion.
2. **Production API and backend deployment.** Local Expo currently targets a private LAN HTTP API. Configure the installed production app to use the deployed HTTPS API. Deploy the matching mobile API and migrations, collect static assets, run production settings checks, and confirm media/private evidence storage, backups and restore procedures. Do not deploy the local preview settings.
3. **Seller-category registration.** Replace free-text category inference with a validated segment choice and migrate/verify existing seller mappings. Current matching recognizes food/restaurant and grocery/groceries/kirana/supermarket; other nonempty values map to merchandise. A value such as “bakery” needs explicit review. Blank categories are blocked with a support prompt. Restrictions are between these three segments, not between every merchandise subcategory.
4. **Native build and signing.** Confirm the real EAS project ID, Android/iOS application ownership, build environments, signing credentials and internal test distributions. The checked-in app config does not include an EAS project ID; it may be supplied externally. Create installed Android/iOS builds and verify native Razorpay, camera, location and background behavior. Expo Go cannot establish native release readiness.
5. **Payments, refunds and settlements.** Verify provider credentials, payment/refund and payout webhook configuration, signature verification, duplicate-event handling and reconciliation in staging. Exercise success/failure, dismissal, lost callbacks, cancellation, partial refunds, refund timeouts/retries, COD remittance and seller payout deductions. Verify currency/amounts and multi-seller ownership. No real payment/refund/payout was initiated in this work.
6. **Production workers and operations.** Verify scheduled notification delivery/receipt processing, checkout-session cleanup, seller payout processing and carrier-status reconciliation. Confirm operations can resolve pending refunds, failed payouts, delivery exceptions and account-deletion requests, with monitoring of failed jobs.
7. **Push and transactional email.** Verify EAS project configuration, FCM/APNs credentials and delivery on installed Android/iOS builds. Test permission denial, foreground/background/cold-start notification navigation and revoked sessions. Confirm signup/reset OTP and order email delivery using the configured email service.
8. **Monitoring and recovery.** Connect the crash-reporting hook to a real provider with native crash capture and source maps; no app-startup binding was found. Add/verify API and worker error alerts, uptime monitoring, backup restoration and a rehearsed compatible rollback.
9. **PostgreSQL staging verification.** Test concurrent stock purchase, seller confirm versus cancel, rider pickup versus cancel, duplicate refunds and payout locking on PostgreSQL. SQLite test success does not prove production locking. Review query counts/load and pagination for realistic seller order volumes.
10. **Device acceptance.** Test the new order list/detail/actions with merchandise, food and grocery sellers. Also verify login/session expiry/logout, catalog/images, carts, checkout, addresses, return flows, uploads, camera permissions, rider GPS/background behavior, poor/offline networks and recovery. Check iPhone/Android layout, large text, screen readers and touch targets. Record actual results rather than inferring them from exports.
11. **Launch content and store submission.** Confirm published support/contact details, privacy/retention/account-deletion information, return/refund terms, permission explanations, store listing assets and review accounts. Complete store submission/review after native device acceptance.

## Optional parity/backlog, depending on launch scope

- Native administrator workspace; current administrative operations remain on the website/Django admin.
- Rich seller sales summaries and detailed finance/settlement breakdowns.
- Mobile category/subcategory requests and standalone restaurant menu-section management.
- Website AI catalog tools and bulk catalog operations.

These parity items need not block a scoped launch if the existing website workflows are accepted operationally. They should not be described as already available in the mobile app.
