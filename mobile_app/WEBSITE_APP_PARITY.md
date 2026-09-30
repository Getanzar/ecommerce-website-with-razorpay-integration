# Website and app comparison

Reviewed 15 September 2026 against the current local workspace, including existing uncommitted work. This is a source review and automated verification, not a certification of the deployed website or an installed Android/iOS release.

## Requested features

| Feature | App status | Evidence / limits |
| --- | --- | --- |
| Online payment: merchandise | Implemented; automated checks pass | Checkout calls native Razorpay; backend verifies signature, captured status, amount and ownership. Pending orders support retry/recovery. |
| Online payment: food and grocery | Implemented; automated checks pass | Same native checkout entry point, service-specific order endpoints and shared payment records. Added tests exercise capture, recovery and foreign-user rejection for both services. |
| Admin dashboard | Missing from native app | Website has operations and management screens. App workspace modes are only seller and rider; there are no corresponding native admin screens or full admin API. |
| Merchandise seller dashboard | Core workflows implemented; partial website parity | Orders, fulfilment/tracking, catalog, inventory, product forms, existing-color variants, payout setup/history and seller cases. Missing items below. |
| Grocery seller dashboard | Core workflows implemented; partial website parity | Seller Center → Grocery: store setup, opening switch, products, stock, orders and payouts. Added checks cover reading sections, changing stock, pausing store and preventing unpaid fulfilment. |
| Restaurant owner dashboard | Core workflows implemented; partial website parity | Seller Center → Food: restaurant setup, opening switch, menu items/options, orders and payouts. Existing tests cover menu creation, option editing, accepting orders and availability. |

The three seller businesses share Seller Center. They are not three separate app dashboards. Approved seller accounts are required; staff status alone does not provide a native administrator workspace.

## Remaining app work, in priority order

### 1. Build the native admin workspace and permission-checked APIs

Port the website capabilities in `dashboard/urls.py`:

- Operations overview, unified order search/detail and order actions.
- Seller approval/suspension and payout verification; customer and rider management.
- Product moderation, catalog/category/subcategory management, inventory and review moderation.
- Delivery assignment/reassignment, exceptions and private proof images.
- Payout management, COD remittance confirmation, shipping reconciliation and service zones.
- Returns, support ticket replies/status, analytics and audit history.
- Administrative seller-case/refund and account-deletion review/execution currently provided through Django admin (`mobile_api/admin.py`). The app exposes customer/seller requests, not administrative execution.

### 2. Complete seller dashboard summaries and finance detail

- Add counts, sales/open-order summaries and available/paid balances comparable to the website seller home screens. The app currently opens lists of orders, catalog or payouts.
- Add aggregate scheduled/processing/paid/on-hold totals and the detailed settlement breakdown shown on the website. The mobile payout endpoint currently returns order, amount, status, schedule and failure reason.
- Surface the seller payout-notification read workflow alongside the existing mobile notification inbox and outstanding return balance.

### 3. Complete merchandise listing creation and catalog workflows

- Add category/subcategory request submission and status history (website `seller/catalog-requests/`).
- Add creation of multiple colors, color images and multiple variants in the listing flow. Mobile creation currently creates one color and one variant; later variant forms can select existing colors but cannot create a new color or upload its image. The website creation flow accepts multiple colors and variants.
- Add the website's AI copy generation, image enhancement, credit purchase and payment-confirmation flow. These do not exist in the mobile partner API/UI.

### 4. Improve business-specific entry and restaurant menu organization

- Completed 20 September: Seller Center selects and displays only the registered segment, with API authorization. Free-text category normalization remains a production-readiness task; see `PRODUCTION_READINESS.md`.
- Add standalone restaurant menu-section creation if matching the website's separate section workflow is required. Mobile can already create/reuse a section by entering its name while editing a menu item.

### 5. Finish release configuration and device verification

These are deployment/testing tasks, not absent payment implementations:

- Test Razorpay success, failure, dismissal, backgrounding, force-close and delayed webhook recovery in installed Android and iOS builds using test-mode credentials.
- Verify the installed app targets the deployed backend and that migrations, webhook configuration and notification workers are deployed.
- Verify store signing, push credentials/delivery, camera/location permissions and accessibility on devices. Connect the provided crash-reporting hook to the chosen production service.

Native Razorpay requires a development/release build; Expo Go and a successful JavaScript export do not verify native checkout. See `RELEASE.md` for the existing rollout checklist.

## Product gallery correction

### App (`App.tsx`)

- Root cause: thumbnail/color/size presses changed `selectedImage`, but the horizontal gallery never scrolled to that image. Variant/color images could also be absent from the slide list.
- Gallery now includes deduplicated product, extra, color and variant images.
- Selection scrolls to the corresponding slide; swipe selection, thumbnail highlight and full-screen preview use the same selected image.
- Slide width comes from the actual gallery layout, including layout changes, instead of relying only on the initial screen width.
- Full product images use contain sizing to avoid cropping. Thumbnail buttons announce selection to accessibility tools.

### Website (`templates/products/product_detail.html`)

- Main images use contain sizing to display the complete product.
- Thumbnail, color and size changes use one selection function that updates the image and thumbnail state together.
- When the main product image is missing, the first available gallery image is selected instead of leaving the placeholder visible.

Physical-device gallery checks remain: thumbnail taps, swiping, color/size selection, full-screen preview, rotation and a product with no main image.

## Verification

- Existing backend suite: 122 tests passed across mobile API, products, dashboard, food, groceries and payments using isolated SQLite test databases.
- Both added tests in `mobile_api/test_parity.py` passed: food/grocery payment capture, recovery and ownership; grocery workspace stock, availability and paid-order/access guards (124 backend tests passed across the two runs).
- Mobile TypeScript check passed.
- All 11 existing mobile tests passed (payment recovery, verification, cancellation, network retries and background tracking).
- Android JavaScript export passed (704 modules). This does not compile the native SDK or install the app.
- Provider calls in automated payment tests are mocked; no real payment or payout was initiated.

Primary source files: `mobile_app/App.tsx`, `mobile_app/src/PartnerWorkspace.tsx`, `mobile_app/src/PartnerForm.tsx`, `mobile_app/src/nativePayments.ts`, `mobile_api/urls.py`, `mobile_api/partner_urls.py`, `mobile_api/partners.py`, `mobile_api/partner_forms.py`, `mobile_api/payment_api.py`, `dashboard/urls.py`, `dashboard/views.py`, `food/urls.py`, `groceries/urls.py`.
