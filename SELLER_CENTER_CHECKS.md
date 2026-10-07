# Seller Center update

Website and mobile now use the same records and validators for Seller profile and food/grocery Store settings. Profile includes business name, description, logo, cover photo, contact number, pickup address and pincode. Store settings include public store photo, description, delivery fees, timings and selected service areas. Listing photos remain editable through Catalog.

Profile and store pickup changes synchronize the active segment's location with the seller record used for delivery coverage. Changing pincode does not automatically expand selected service areas: review those in Store settings. Approval, business segment, commission and payout authorization remain marketplace-controlled.

## Deployment

- Deploy the GitHub update to Render. Migration `accounts.0013` adds the optional description, logo and cover fields. The repository's Procfile runs migrations before startup; verify your Render start command uses that migration step.
- Photos need persistent production media storage, such as the configured Cloudinary backend. Verify uploads survive a Render restart.
- Build and install a new mobile release to receive the updated native screens. A GitHub push updates source; it does not update an installed app binary.

## Manual checks after deployment

1. Sign in as an approved merchandise, food and grocery seller separately. Open Seller Center and verify the correct Catalog, Orders, Payouts and Seller profile links. Food/grocery sellers also have Store settings.
2. Edit Seller profile: business name, description, logo, cover and contact information. Capture GPS while at the pickup location, then save. Confirm a success message and the updated header/photo after reload.
3. In the updated app, open Seller Center → Edit seller profile. Confirm the website changes, replace a photo, capture GPS and save. Reload the website and confirm the same record changed.
4. Open food/grocery Store settings and update public photo, description, fees, timings and service areas. Check the public store page and both seller clients. Profile logo/cover are Seller Center branding; public food/grocery pages use the store photo.
5. Edit one product/menu photo from Catalog. Verify it on the buyer website and app. On an existing listing, leaving the photo untouched must retain it.
6. Remove an optional profile/store photo and save. Confirm the saved preview disappears on both clients. Try an invalid file and an image over 8 MB: saving should fail with an error.
7. If pickup pincode changes, verify it in the operations delivery-coverage dashboard and review service areas. Confirm a test order uses the new pickup details.
8. Pause/reopen the food/grocery store, verify its buyer availability, and check a paid test order in Orders and Payouts.

Automated checks cover cross-client edits, photo retention/removal, pickup synchronization, segment restrictions and seller ownership. Native device permissions, production photo persistence and live payments still require device/deployed checks.
