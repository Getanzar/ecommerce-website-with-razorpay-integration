# Small sellers without GSTIN

## Customer-facing entry

`/accounts/sell-with-us/` shows two options before login:

- Small seller without GSTIN: `/accounts/sell-with-us/small/`.
- Registered business: `/accounts/sell-with-us/registered/`.

New-account links carry a fixed seller route through email verification. Existing profiles retain their registration type and existing approved sellers return to their workspace.

## Application and review

Small sellers provide legal/business details, local pickup GPS, contact details, Aadhaar last four digits, a masked Aadhaar image, bank details, consent to private image storage and review, and an eligibility declaration. No PAN or GST enrolment fields are requested by this form. The upload accepts JPG, PNG and WebP up to 8 MB. Sellers must hide the first eight Aadhaar digits and leave the name, photo, last four digits and Secure QR visible.

Images are stored outside public media at `PRIVATE_MEDIA_ROOT/seller_identity` with random filenames. Configure this directory on persistent private storage; never expose it through the web server. The operations dashboard serves images only to authorised operations admins with no-store response headers and audits document access. Django admin links to the same protected route. Mobile application schemas use the existing image picker and multipart upload support.

Admins open the seller in Seller Management, inspect the uploaded photo, compare the name and last four digits, confirm both document and eligibility checks, and record an internal reference. A new verified review requires an uploaded image. This is manual document review, not automatic UIDAI authentication. Official UIDAI QR tools can be used when checking document authenticity. Existing verified sellers retain their status; new applications and resubmissions require the image.

Identity review, seller approval and payout activation remain separate actions. Corrections appear to the seller. Resubmission invalidates the previous review and payout tokens. Replaced images and documents belonging to deleted sellers are removed after the database transaction commits. Withdrawing consent deletes the photo, clears the Aadhaar suffix and review, suspends selling and disables payouts.

## Merchandise behavior

Approved small sellers use the existing products, variants, inventory, moderation, orders, returns and payouts. Seller product forms omit merchandise GST; buyer totals retain applicable platform-fee GST. Small-seller GST TCS is zero. Merchandise delivery remains seller-sponsored.

The initial selling scope is local delivery within the reviewed pickup pincode, with active local coverage. Checkout rejects another pincode and never falls back to Delhivery for small-seller parcels. Pickup pincode cannot be changed through seller settings. Support must review eligibility and location before any change. Registered business routing and tax treatment remain unchanged.

## Deployment

Apply the schema migration before serving this code:

```powershell
python manage.py migrate
```

Migration `accounts.0017_sellerprofile_aadhaar_image` adds the private document field.

Migration `accounts.0014_small_seller_registration` defaults existing sellers to the registered-business route. It does not change existing seller status, tax or payout eligibility. Ensure the deployment's normal database and RazorpayX configuration are available. Product moderation and local rider coverage remain prerequisites for customer orders.

Use the applicable current turnover threshold for the seller's registered state; there is no blanket Aadhaar-only exemption. Staff should monitor eligibility and move sellers to registered-business onboarding when registration becomes required. Do not approve this route without completing the real identity and GST-enrolment checks.

## Primary references

- GST Council newsletter, October 2023, GSTN enrolment advisory: https://gstcouncil.gov.in/sites/default/files/2024-02/october_newsletter.pdf
- UIDAI offline verification guidance: https://www.uidai.gov.in/images/DosandDon_ts_for_Offline_Verification_Seeking_entities.pdf
- UIDAI updated Aadhaar authentication and offline verification regulations: https://www.uidai.gov.in/images/The_Aadhaar_Authentication_and_Offline_Verifications_Regulations_2021-_Clean_copy-30122025.pdf
