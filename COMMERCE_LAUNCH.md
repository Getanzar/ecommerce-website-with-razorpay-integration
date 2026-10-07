# Payment and delivery launch audit — 6 October 2026

Status: NOT cleared for public shopping. Local configuration is not proof of the production configuration.

Validation: all 214 backend tests passed using isolated SQLite, including three
new payment/courier regression tests. Live providers, PostgreSQL concurrency,
Render environment and physical deliveries were not verified.

## Changes made

- Website food/grocery payments now verify captured status, provider order, amount and INR currency directly with Razorpay before recording payment.
- Added `book_delhivery_shipments` for persisted mobile/web parcel charges. It skips unpaid/cancelled orders and existing AWBs, and locks each package during booking. Ambiguous failures are left for carrier reconciliation, not automatically retried.
- Corrected prepaid carrier mode to `Pre-paid`. Pickup location is now configured through `DELHIVERY_PICKUP_LOCATION`; enter the exact registered warehouse name, not an assumed street address.
- Added `check_commerce_launch`, a read-only configuration check. It does not reveal credentials or prove provider activation.

## Configuration blockers found locally

1. `RAZORPAY_WEBHOOK_SECRET` missing. Set a new webhook secret and use the same value in Razorpay's webhook dashboard for `https://YOUR-DOMAIN/payments/webhooks/razorpay/`. Subscribe to captured, failed, order-paid and refund events. Verify retries and duplicate deliveries.
2. `DELHIVERY_PICKUP_LOCATION` missing. Set the registered platform warehouse name; each seller shipping from another origin must have their own registered `delhivery_pickup_name`.
3. `RAZORPAYX_KEY_ID` and `RAZORPAYX_KEY_SECRET` missing. The payout account number alone cannot send seller/rider earnings. Verify funded RazorpayX account and recipient fund accounts before enabling payouts.
4. `DEBUG` enabled and HTTPS redirect disabled locally. Verify production uses `DEBUG=False` and `SECURE_SSL_REDIRECT=True`, with correct trusted proxy settings.
5. Delhivery fallback quotes enabled. Set `DELHIVERY_REQUIRE_LIVE_QUOTE=True` in production before enabling courier checkout.

Do not copy test values into live configuration. No production credentials or settings were changed by this audit.

## Production rollout

Deploy these backend changes and run migrations. Run `python manage.py check_commerce_launch` and `python manage.py check --deploy` on the production host.

Schedule `python manage.py book_delhivery_shipments` regularly (for example every five minutes), and `python manage.py refresh_delhivery_shipments` every 15–30 minutes. Booking dry run: `python manage.py book_delhivery_shipments --dry-run`.

Schedule `send_mobile_notifications`, `cleanup_checkout_sessions`, and the established seller/rider payout commands. Confirm jobs actually execute and alert on failures. The booking command creates manifests; physical pickup requests and packing labels still require the carrier operational workflow. Check serviceability of launch destinations with Delhivery before promising coverage.

Inspect packages with `manifestation_failed` or `manifestation_pending` in the admin. First query Delhivery using the unique shipment order reference (`order ID-seller ID`, or `order ID-platform`). If created, record its AWB. Reset the carrier status to blank for a retry only after confirming the carrier did not create it. Never retry an ambiguous booking blindly.

## Acceptance before inviting customers

- Pay for a small order on the deployed website and installed app. Confirm correct amount, captured state, one order, stock deduction and seller notification. Close the browser after payment to verify webhook recovery. Test failed payment, duplicate callback, cancellation and refund.
- Courier: confirm actual AWB, registered seller pickup, printable label, pickup request, physical collection and tracking updates through delivery. Confirm final invoice reconciliation and COD remittance.
- Local: approve an online rider for each active pincode. Verify seller pickup GPS and customer GPS, food/grocery ready action, one rider claim, pickup, customer OTP email, OTP completion, customer order state, rider earnings and COD handover. Verify Brevo delivers real messages.
- Verify payout timing matches the business decision and run a small seller and rider payout before enabling automatic live transfers.
- Use staging/production PostgreSQL to verify simultaneous rider claims and booking workers; SQLite tests do not validate production row locking.

Public launch remains pending until configuration and these real provider/device/physical delivery checks pass.
