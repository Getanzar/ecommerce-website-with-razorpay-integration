# Launch progress and handoff

Latest payment/carrier/rider audit: 6 October 2026. See `COMMERCE_LAUNCH.md`
for the current blockers and rollout steps. Added authoritative website
food/grocery capture verification, a guarded carrier booking command, and a
read-only launch configuration check. Production rollout and physical acceptance
remain incomplete; the earlier mobile carrier-booking gap now has a command
but still needs scheduling and provider verification.

Audit date: 28 September 2026. First implementation batch added on this date.

Verified baseline: 185 backend tests passed on SQLite; 21 mobile tests passed;
TypeScript passed; migration consistency passed. Local deployment check reports
DEBUG enabled, HTTPS redirect disabled and HSTS disabled. Production accounts,
native builds, provider transactions and physical devices remain unverified.

## Working agreement

Check account usage between meaningful batches. Aim to stop implementation at
about 80% of the current five-hour allowance, leaving room for verification and
handoff. Limits are account-wide and may change from other chats; a guaranteed
last message before a hard cutoff is not possible. Update this file after each
completed batch with changes, tests, unfinished work and external dependencies.

## Remaining checklist (numbers match the chat audit)

- [x] 1. Upgrade to Django 5.2.17 LTS; local dependency check and 201-test suite passed; CI now covers Python 3.12/3.13. Production upgrade and PostgreSQL validation remain.
- [ ] 2. Set and verify production mobile API build environment.
- [ ] 3. Verify secure production settings.
- [x] 4. Add signup OTP resend and unfinished-signup recovery (code; installed-device acceptance pending).
- [ ] 5. Authentication throttling/cooldowns and shared cache support implemented; production cache creation and proxy validation remain.
- [x] 6. Apply Django password validators during mobile signup.
- [ ] 7. Explicit segment field, registration choices, authorization and conservative data migration implemented and locally tested; production migration and legacy-record review pending.
- [ ] 8. Complete reliable mobile courier dispatch or restrict launch coverage.
- [x] 9. Validate customer cart quantities/IDs, product price/rating filters, checkout address IDs and submitted food/grocery items. Broader API fuzzing remains part of release QA.
- [ ] 10. Backend shop/grocery catalog pagination is now present (24/page, max 50), but mobile getProducts still discards next-page metadata and has no page parameter. Complete app loading and regression tests before launch.
- [ ] 11. Integrate and verify crash reporting.
- [ ] 12. Publish real policies and replace placeholder links.
- [ ] 13. Audit tracked database backups and any historical exposure.
- [ ] 14. Review release changes and verify a reproducible deployment commit.
- [ ] 15. Deploy matching backend, migrations and static assets.
- [ ] 16. Verify public domain, HTTPS and API from an external phone.
- [ ] 17. Verify PostgreSQL concurrency and locking.
- [ ] 18. Verify durable public/private media storage and access controls.
- [ ] 19. Configure backups and rehearse restoration.
- [ ] 20. Schedule notifications, checkout cleanup, payouts and carrier refresh.
- [ ] 21. Verify Brevo sender/domain and transactional mail delivery.
- [ ] 22. Configure monitoring and rehearse compatible rollback.
- [ ] 23. Verify Razorpay activation and credentials.
- [ ] 24. Configure and test payment/refund webhooks.
- [ ] 25. Test installed-app payment flows for every enabled segment.
- [ ] 26. Test refunds, cancellations and support handling.
- [ ] 27. Decide and enforce seller payout timing.
- [ ] 28. Verify RazorpayX funding, accounts, webhooks and payout reconciliation.
- [ ] 29. Verify COD collection and remittance reconciliation.
- [ ] 30. Confirm delivery deductions and order economics with business owner.
- [ ] 31. Prepare service areas, sellers, riders and carrier operations.
- [ ] 32. Resolve or clearly communicate remote-address GPS limitation.
- [ ] 33. Populate and approve real catalog and stock.
- [ ] 34. Link owned EAS project and build environment.
- [ ] 35. Configure store ownership and signing credentials.
- [ ] 36. Build and install signed native release candidate.
- [ ] 37. Configure and verify FCM/APNs push delivery.
- [ ] 38. Verify camera and background-location permissions on devices.
- [ ] 39. Publish privacy, retention, support and public deletion pathway.
- [ ] 40. Prepare store assets, declarations and reviewer access.
- [ ] 41. Complete applicable store testing requirements.
- [ ] 42. Complete physical-device acceptance checklist.
- [ ] 43. Complete limited operational pilot.
- [ ] 44. Publish approved store download links.
- [ ] 45. Optional: native administrator workspace.
- [ ] 46. Optional: advanced seller analytics, AI and bulk tools.
- [ ] 47. Optional: additional seller catalog and restaurant organization tools.

## First implementation batch and resume instructions

Implemented signup resend/resume UI and endpoint; signup password/identity
validation; authentication account/IP limits and email cooldowns; shared database
cache configuration and deployment warning; locked OTP verification and guards
against reactivating verified disabled accounts; removed dangerous signup error
cleanup; validated customer numeric inputs and normalized checkout item IDs.

Usage reached 89% of the five-hour allowance at the checkpoint. New feature work
stopped to finish verification and handoff. Reset reported: 29 September 2026,
03:28 IST. Do not automatically consume the available reset credit.

Validation complete: full 201-test backend suite passed on isolated SQLite;
TypeScript passed; 22 mobile tests passed; migration consistency passed. Native
build and physical-device verification were not performed. Repository-wide diff
check found pre-existing trailing whitespace in payments/tests.py:272; that file
was not modified in this batch.

Deployment actions for this batch: set DJANGO_CACHE_TABLE=ziyamart_cache and run
manage.py createcachetable before workers start; verify trusted proxy configuration
and distinct client IPs; deploy backend before app; verify actual Brevo delivery,
resend UI and recovery on installed devices. No production changes performed.
DRF rate counters are best-effort under concurrency; use edge abuse protection.

Next code priorities: finish customer pagination with app compatibility (10),
then mobile courier dispatch (8). Django upgrade and explicit seller segment
code are complete; deployment verification remains. All unchecked items above remain unfinished. Existing
user edits were preserved; no commit, push, store build or deployment performed.

## External dependencies

Production host/database access; provider credentials and account activation;
business decisions and policy details; EAS/store ownership and signing; physical
devices/testers; verified seller/rider/catalog data. Never mark these complete
based only on local code or mocked tests.

## Second batch: framework upgrade

Resumed after the account allowance reset (5% used at resume; 37% at next
checkpoint). Installed Django 5.2.17 LTS in the existing project virtual
environment, updated requirements.txt (converted its UTF-16 encoding to UTF-8),
and configured CI for Python 3.12 and 3.13. pip check passed. Migration check
reported no changes. Initial 201-test run found 10 errors from upload tests
overriding STORAGES without the staticfiles alias. Corrected all three affected
test fixtures; full 201-test rerun passed on Django 5.2.17.

Implemented explicit seller business_segment with choices shop/food/grocery;
registration and mobile dynamic form use choices, authorization no longer infers
segments from free text, and web menus/routes use the same field. Migration
accounts.0012 preserves original category text and backfills exact known labels;
unknown/mixed labels stay blank for admin review. Existing seller fixtures now
set explicit segments. Final suite passed all 204 tests; migration consistency
passed. Production
migration and review have NOT been run. No native build/deployment performed.

## Status review: 30 September 2026

Reviewed current files and the saved successful 204-test log; did not rerun the
suite during this status-only review. CatalogPagination is now present in the
backend but is not integrated with mobile next-page loading; the earlier test
result does not certify this newly observed change. Local mobile API still uses
a private LAN HTTP address; crash reporter remains unbound; signup terms link
remains a placeholder. External deployment/provider/store readiness remains
unverified. Of 44 launch checklist entries, four are marked complete locally,
two more have implementation complete but production setup/review pending, and
38 others remain open (some partial). Three additional entries are optional.
These are checklist counts, not a percentage of coding effort or launch readiness.

## Pagination batch: 30 September 2026

Implemented paged shop/search/category loading and grocery-store product loading
with Load more, retry preserving existing rows, cancellation/stale-response
protection, duplicate-row suppression, and server-side grocery search/filters.
New grocery metadata requests omit embedded products; old clients retain the
existing response by default. Catalog ordering now includes a unique ID tie-break.
Added pager and backend page-boundary tests. Validation running at checkpoint.

Usage reached 81% before testing, so no new task was started. Production-build
safeguards and tracked-backup audit are NOT completed and are the next tasks.
Do not consume a reset credit automatically. No deployment or native build.
