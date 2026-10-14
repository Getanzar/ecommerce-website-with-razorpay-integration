# Small sellers without GSTIN

## Customer-facing entry

`/accounts/sell-with-us/` shows two options before login:

- Small seller without GSTIN: `/accounts/sell-with-us/small/`.
- Registered business: `/accounts/sell-with-us/registered/`.

New-account links carry a fixed seller route through email verification. Existing profiles retain their registration type and existing approved sellers return to their workspace.

## Application and review

Small sellers provide legal/business identity, local pickup GPS, contact details, Aadhaar last four digits, PAN, GST-portal enrolment, bank details, identity-verification consent and an eligibility declaration. Full Aadhaar numbers/documents are never requested or uploaded. PAN and bank account numbers are transient form inputs; only suffixes are saved.

Submitting last-four digits is not Aadhaar verification. Applications remain pending. The marketplace's authorized verification team must arrange an offline review, verify the Aadhaar Secure QR with official UIDAI tools, confirm identity/name and check GST-portal enrolment, PAN match, registered state and turnover eligibility. This release has no UIDAI OTP, biometric or GSTN validation API integration. Staff must perform the actual checks before recording a verified review.

In Seller Management, use the Small sellers filter, open the seller and record both completed checks and an internal review reference. Identity review does not approve the seller or activate payouts. Marketplace approval opens the standard merchandise workspace. Bank setup uses the existing RazorpayX integration; payout activation remains a separate staff action. Corrections are shown to the applicant. Resubmission invalidates previous verification and bank tokens. Identity consent, withdrawal and review actions are audited without full identity numbers.

Consent can be withdrawn from the application or seller settings. Withdrawal clears retained Aadhaar digits and verification details, suspends selling, hides products and disables payouts. A new reviewed application is required before selling resumes.

## Merchandise behavior

Approved small sellers use the existing products, variants, inventory, moderation, orders, returns and payouts. Seller product forms omit merchandise GST; buyer totals retain applicable platform-fee GST. Small-seller GST TCS is zero. Merchandise delivery remains seller-sponsored.

The initial selling scope is local delivery within the reviewed pickup pincode, with active local coverage. Checkout rejects another pincode and never falls back to Delhivery for small-seller parcels. Pickup pincode cannot be changed through seller settings. Support must review eligibility and location before any change. Registered business routing and tax treatment remain unchanged.

## Deployment

Apply the schema migration before serving this code:

```powershell
python manage.py migrate
```

Migration `accounts.0014_small_seller_registration` defaults existing sellers to the registered-business route. It does not change existing seller status, tax or payout eligibility. Ensure the deployment's normal database and RazorpayX configuration are available. Product moderation and local rider coverage remain prerequisites for customer orders.

Use the applicable current turnover threshold for the seller's registered state; there is no blanket Aadhaar-only exemption. Staff should monitor eligibility and move sellers to registered-business onboarding when registration becomes required. Do not approve this route without completing the real identity and GST-enrolment checks.

## Primary references

- GST Council newsletter, October 2023, GSTN enrolment advisory: https://gstcouncil.gov.in/sites/default/files/2024-02/october_newsletter.pdf
- UIDAI offline verification guidance: https://www.uidai.gov.in/images/DosandDon_ts_for_Offline_Verification_Seeking_entities.pdf
- UIDAI updated Aadhaar authentication and offline verification regulations: https://www.uidai.gov.in/images/The_Aadhaar_Authentication_and_Offline_Verifications_Regulations_2021-_Clean_copy-30122025.pdf
