# ZIYAMART security and app review — 25 October 2026

## Assessment

The website and mobile app share one backend, but they did not have complete UI/feature parity at the start of this review. The main current customer/seller gaps have been implemented. Administrative mutations still use the existing secure website, launched from the app. Installed-device acceptance and signed release verification remain necessary.

This is source review, automated regression testing, dependency auditing and a few read-only public HTTP checks. It is not a penetration test or a guarantee that the website cannot be compromised.

## Verified security findings and changes

1. **Production debug information was exposed.** An ordinary request to a nonexistent page returned Django's detailed debug page. Hosted configuration now forces DEBUG=False when RENDER=true or DJANGO_ENV=production, even if DEBUG=true is configured. The fix was pushed separately as ca79b82. A subsequent live check confirmed a generic 404 and `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`.
2. **Browser authentication was missing rate limits.** Website/admin login and account email actions now have hashed per-identity and peer-address limits, a 429 response and Retry-After. Existing mobile authentication limits remain. Production defaults to the shared database cache; migration 0018 creates its table. The Procfile collects static assets, runs migrations and creates the configured cache before starting workers.
3. **API defaults were overly permissive.** The default is now authenticated access. Public catalog/authentication endpoints explicitly retain public access. Seller/rider/customer ownership and operations permission checks remain server-side.
4. **Historical credentials existed in Git.** Four historical commits touched the root .env and contained credential values. The owner confirmed production credentials were already rotated. This confirmation is not independent provider verification. Some old values still match local .env; treat local configuration as stale until it is updated privately. No credential values are reproduced here. Current environment files are ignored, not tracked. History was not rewritten.
5. **Dependency advisories.** OSV initially flagged nine Python packages. The patched, resolver-compatible requirements now return zero advisories for the 36 pinned packages checked; pip check reports no broken requirements. Compatible app tooling overrides reduced the pnpm production dependency audit from 10 advisories to two high advisories: node-forge 1.4.0 (GHSA-86w9-cpqp-85rv) and zod 3.25.76 (GHSA-mrhx-c7xc-m3w5), through Expo CLI. The audit is not clean. An incompatible major Zod override was not forced; node-forge had no patched version in the audit result. These dependency findings do not by themselves demonstrate an exploit against the Django website or native customer application. Keep Metro/development tooling off public ingress and follow upstream fixes.
6. **Live access checks.** Anonymous seller roles returned 401. Public home/catalog returned 200. Live responses included X-Frame-Options=DENY, X-Content-Type-Options=nosniff and Referrer-Policy=same-origin. HSTS was absent before the hotfix and present afterward.

## Validation

- 452 backend tests passed on isolated SQLite, including payments, authentication, ownership, orders, sellers, delivery, catalog and new electronics/admin/finance coverage. Payment/provider failures in logs were intentional mocked regression scenarios.
- A further 59 targeted dashboard/product/API checks passed after adding server-side positive-price, GST-range and positive-package validation; the minimum electronics price uses Decimal arithmetic.
- 45 app tests passed; TypeScript passed after the compatible dependency overrides.
- Production `manage.py check --deploy` passed with RENDER=true even when DEBUG=true was supplied. CI now checks production configuration as well as backend tests and both platform exports.
- Android and iOS production Hermes exports passed (751 modules per platform).
- Windows arm64 Android debug compilation passed. A fresh Expo prebuild and subsequent compilation also passed. The build fixes use pnpm's hoisted layout and a source-controlled Expo config plugin that shortens the Windows CMake staging path. Generated autolinking caches from the old installation were refreshed.
- EAS signed internal Android build ef374696-5084-41d3-acb6-08fbd07c3147 finished successfully from source commit 8858df1. The APK is 80,955,998 bytes, package in.ziyamart.app, version 1.2.0 / code 2. Android apksigner verification passed; its signing certificate differs from the debug certificate, the APK is not debuggable, and its embedded bundle contains https://www.ziyamart.in/api/v1.
- APK SHA-256: 8dc52c725e234380004e0b397f36abf499446a49d616cdf5a7ef5759299da0f9. Signing-certificate SHA-256: 0ced1ac716f1fda0e4c90da80d6635e81fcb7e238cdf5d3638f4a3e1f3002676.
- Internal build page: https://expo.dev/accounts/ziyamart/projects/ziyamart/builds/ef374696-5084-41d3-acb6-08fbd07c3147 . A verified local APK and machine-readable receipt are in the ignored mobile_app/build/ directory. The APK was not published to Google Play.
- No phone or emulator was connected during verification. Installed-app UI, live/test-provider payment acceptance, actual push receipt and background GPS remain unverified.
- No real payment, refund, payout, customer order or seller listing was created on production for this review. Public live requests were read-only.

## Boundaries and remaining work

Native admin mutation screens are not a one-for-one replacement of the website; the app opens the audited web workflows. The signed internal Android APK is available; physical-device acceptance and any store submission are still required. Production payment/webhook/push credentials, scheduled workers, PostgreSQL race behavior, backup restoration and provider-side key rotation cannot be certified by SQLite/mocked tests. The local native Android release configuration uses a debug signing configuration; use the existing EAS production signing workflow for an actual store release, not a locally debug-signed APK.

## References

- Django deployment checklist: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Render's built-in production marker: https://render.com/docs/environment-variables#render
- Expo SDK 57: https://docs.expo.dev/versions/v57.0.0/
- OSV package/version query: https://google.github.io/osv.dev/post-v1-querybatch/
- Remaining tooling advisories: https://github.com/advisories/GHSA-86w9-cpqp-85rv and https://github.com/advisories/GHSA-mrhx-c7xc-m3w5
