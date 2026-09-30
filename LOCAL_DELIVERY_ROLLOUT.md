# Local delivery and order notifications

Implemented in this development step:

- Mobile local checkout requires a fresh delivery GPS fix explicitly captured for the selected address. Address, location, items and financial totals are bound to the checkout quote. Changed data requires a new quote.
- Mobile orders retain delivery coordinates and seller delivery-charge records. No database migration is needed for these fields.
- Local merchandise COD orders create rider jobs at checkout; online orders wait for server-confirmed payment. Food and groceries create jobs when the seller marks the order ready, after payment for online orders.
- Approved online riders in the matching pincode receive an inbox event. The existing claim endpoint locks the job before assigning it.
- Website and mobile checkout use a shared seller alert function. Online orders wait for confirmed payment; retries do not duplicate the new-order alert.
- New mobile local orders without a pickup GPS fix are rejected. Legacy food/grocery orders with missing GPS cannot be marked ready through the mobile seller endpoint; they require correction through an appropriate operational workflow.

## Deployment and verification

The repository currently ignores `mobile_api/` and `mobile_app/` as separately maintained projects. Their changed source files must be included in the relevant backend/mobile deployment; committing only the root repository changes is insufficient.

Restart the backend and reload/rebuild the mobile app after deploying both sides together. Old local-checkout clients without GPS support will receive a location-required error. Previously generated quotes may require refresh.

Run the isolated regression suites with `--settings=config.test_settings`. The dedicated `mobile_api.test_checkout_delivery` suite rejects live HTTP calls and covers order placement, readiness, seller/rider notifications, payment gating, quote tampering and rider claiming.

On a test device, select the actual delivery address while physically there, then use the checkout location button. Check the seller inbox, mark food/grocery ready, and claim the resulting job from an approved online rider account with the same pincode. Existing OTP completion and earnings tests cover delivery completion separately.

## Still requires a separate production rollout

- Remote phone push requires an installed development/release app, EAS/native push credentials, permission, and an active device token. Expo Go does not register for push in this app. Schedule `send_mobile_notifications` on the backend to deliver persisted inbox events.
- This step does not enable or schedule live payments, payouts, push sending, or carrier requests. Do not treat an inbox event as proof a device received push.
- Nonlocal mobile merchandise orders now retain shipment-charge information, but automatic Delhivery booking/pickup is not enabled by this step. A durable booking worker, retry/reconciliation policy, registered seller pickup locations and tested carrier credentials are still needed. Existing website carrier behavior is unchanged.
- Razorpay/RazorpayX live credentials, public HTTPS webhooks, account activation/funding, seller/rider verification and scheduled payout reconciliation remain operational setup. Existing payout timing is unchanged; decide whether online seller payouts should wait for delivery before activating live payouts.
- GPS is a client-provided delivery pin with range/accuracy/freshness validation, not proof that the physical address or pincode matches the coordinates. This version explicitly supports capturing at the selected delivery address; remote-address pin selection is a separate feature.
- Older orders missing delivery data are not automatically backfilled or dispatched.
