# Merchandise delivery paid by the customer

New merchandise checkouts follow this sequence:

1. The customer enters a delivery address, verifies GPS, and chooses online payment or COD.
2. Checkout groups items by seller and calculates packed chargeable weight.
3. Courier packages request a live Delhivery Surface quote using the seller's origin PIN, customer PIN, weight, and payment mode. Local packages retain the existing local rider pricing.
4. The customer reviews the delivery-inclusive total and each seller's delivery charge. Web quotes expire after five minutes. Changing the address, cart, GPS location, or payment method requires review again.
5. Only confirmation creates a Razorpay payment order or a COD order. The accepted delivery amount is saved with the order; it is not charged separately later.

Delhivery `total_amount` includes its taxes. Checkout passes this total through without a handling markup or adding GST again. A missing, zero, invalid, or unavailable live courier rate blocks new production courier checkout rather than displaying free delivery or a guessed price. Delhivery rates are estimates; carrier adjustments remain a platform reconciliation expense, not a new customer collection or seller deduction.

Each new merchandise delivery quote stores `delivery_payer: customer`. Seller settlement creation and final carrier-bill reconciliation use this saved policy, so the seller's delivery deduction remains zero. Existing orders and saved payment transactions retain their original policy. Food and grocery delivery policies are unchanged.

The customer pays ZIYAMART (via Razorpay or COD). Delhivery continues to debit the platform's courier account/wallet. Keep that wallet funded and register each seller's actual pickup address. Shipment booking is separate from scheduling collection after packing.

Mobile API checkout uses the same merchandise pricing. Updated mobile source sends the selected payment method when fetching a quote and refreshes the quote when that method changes; distributing those client changes requires a new app build.

Validation: full Django suite, delivery review/payment/COD regressions, multi-seller totals and tax checks, seller payout reconciliation checks, mobile type check, and mobile tests.
