# Website and app parity — 25 October 2026

The website and app use the same Django backend, accounts, sellers, products, variants, stock, orders, settlements, and delivery records. Browser sessions and mobile device sessions are separate. Equivalent workflows do not mean identical layouts, and automated tests do not establish physical-device readiness.

## Current comparison

| Area | Website | App |
| --- | --- | --- |
| Accounts | Email OTP, login/recovery, Google, profile | Native equivalents using shared validators and backend |
| Categories | Category/subcategory images and icons | Native category symbols, subcategory chips, same catalog |
| Electronics | Five types, existing accessory categories, technical specifications | Electronics category and five filters, same legacy-category matching and specifications |
| Merchandise sellers | Business-specific dashboard, forms, approval, inventory, orders | Business-specific electronics choices/forms, shared approval and inventory, grouped orders |
| Food/grocery sellers | Store settings, menu/catalog, variants, availability, orders | Native shared-schema forms and APIs; standalone menu-section creation added |
| Seller finance | Sales/order summaries and settlement breakdown | Sales/order summaries, scheduled/processing/paid/on-hold/failed balances and deduction/delivery/TCS detail |
| Catalog tools | Categories/subcategories, photos, variants, listing assistant | Existing native taxonomy/color/variant tools and assistant; electronics uses the same assistant |
| Customer purchase | Carts, quotes, COD, Razorpay, orders, invoices, reviews, returns and support | Existing native flows, using shared payment and order services |
| Rider work | Assignment, pickup, collection, OTP, evidence, tracking, earnings | Existing native workspace and scoped background tracking |
| Administration | Full operations and Django admin workflows | Permission-checked native overview and review queue; management actions open the secure website with separate administrator login |

## Changes in this review

- Public category API includes icons, Electronics even when empty, and the five electronics type definitions.
- Electronics queries include existing Mobile accessories/Home appliances categories. Out-of-stock, pending, suspended-seller and inactive listings remain excluded.
- New native electronics product schema endpoints reuse the website ElectronicsProductForm. Fields are category-specific; existing electronics edits preserve specifications and cannot change stock through disabled quantity fields.
- Seller workspace returns only that seller's electronics choices, sales/order metrics and settlement balances. Food/grocery access remains controlled by the approved business segment.
- Standalone food menu sections reuse the website form and are restricted to food sellers.
- Native administrator overview requires the same explicit operations permission as the website. Staff status alone is insufficient. No device token is passed to the browser or placed in a URL.
- Production debug/rate-limit configuration and vulnerable dependencies were addressed; see ../SECURITY_REVIEW.md.

## Release acceptance still required

- Native admin mutations remain website workflows; they are not implemented as separate native screens.
- Android debug compilation and a fresh prebuild followed by compilation passed. A signed, non-debuggable internal APK was built through EAS and verified. No Android device or emulator was connected; see ../SECURITY_REVIEW.md for the artifact and verification receipt.
- Android/iOS JavaScript exports do not prove native Razorpay, Google handoff, camera, push notifications or background GPS on installed builds.
- Validate OTP delivery, test-mode payment success/failure/recovery, notifications, rider pickup/completion and cross-platform order visibility on signed internal builds. Verify PostgreSQL concurrency, production workers and backup restore separately.
- Existing installed apps need a new build containing the UI changes; a Render deployment updates only the backend/website.
