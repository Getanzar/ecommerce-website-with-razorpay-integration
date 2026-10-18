# Seller listing assistant

Available inside merchandise Add product, grocery Add/Edit product, and food Add/Edit menu item on the website, and the corresponding product forms in the mobile Seller Center. Every approved seller can use it for their saved business segment, including small sellers. No AI subscription is required.

Choose a fresh main product photo (and optionally a back photo), enter up to 2,000 characters of factual notes, generate a draft, review it, then apply it. Existing saved photos must be selected again to send them for analysis. Generation makes no product, order, inventory or payment changes. Applying a draft only updates supported name/description/category fields, and grocery brand/pack-size fields. Food menu sections are limited to that seller's restaurant. Colour/keyword suggestions and details to confirm are displayed for review. Price, MRP, tax, stock, food type, variants and publishing remain manual.

## Live website and mobile setup (Render)

Both clients use the same Django backend. Configure Gemini once on that backend; sellers do not need their own Google accounts or API keys. The app's production API is `https://www.ziyamart.in/api/v1`.

### 1. Create a Gemini key

Open [Google AI Studio](https://aistudio.google.com/), sign in, select or create the Google Cloud project for Ziyamart, and open Dashboard → API Keys → Create API key. If Google asks you to accept terms or enable billing, complete those steps in your own account. Use the project's paid tier for production capacity and its data-use terms; free-tier limits can interrupt a busy marketplace. Review project quotas and configure Google Cloud billing alerts. Alerts do not themselves stop API spending.

Keep the key in your backend environment. Never paste it into this chat, commit it to Git, or add it to mobile/Expo/browser settings. New keys from AI Studio use Google's current authentication format. If an older key is rejected, create a new Gemini key in AI Studio and update Render.

### 2. Configure the existing Render website service

Open [Render Dashboard](https://dashboard.render.com/), select the Django service serving ziyamart.in, then Environment. Add/update:

```dotenv
GEMINI_API_KEY=your_private_Gemini_key
SELLER_LISTING_AI_MODEL=gemini-3.1-flash-lite
SELLER_LISTING_AI_DAILY_LIMIT=20
```

The key above is a placeholder; enter the real key only in Render's environment editor. Save the environment changes. Explicitly replace an existing `gpt-4.1-mini` model value if you previously configured it. This feature no longer reads `OPENAI_API_KEY`. It reads `GEMINI_API_KEY` only, not `GOOGLE_API_KEY`.

`gemini-3.1-flash-lite` supports images and structured output. If Google does not enable it for your project, select an available Gemini model with these capabilities in AI Studio and update the model variable. No automatic provider fallback is made. Do not rely on access to the cheaper Gemini 2.5 models for a new project; Google restricts those to previous active users.

### 3. Deploy the backend and website code

Publish the reviewed code changes to the Git branch connected to your Render service, including the new `dashboard/migrations/0002_sellerlistingaiusage.py` migration, assistant modules, templates, management command and static script. In Render → Events, wait for that commit to become Live; use Manual Deploy → Deploy latest commit if necessary.

Under Render Settings, confirm the existing build process installs requirements and runs `python manage.py collectstatic --noinput`. Preserve other required build steps. Confirm migrations run against the production database. This repository's Procfile includes migrations and cache-table creation before Gunicorn, but Render's saved Start Command is the actual command used. If it does not already run migrations, run them through the production deployment process or Render Shell:

```bash
python manage.py migrate --noinput
python manage.py check_listing_assistant --verify-provider
```

Expected output includes the Gemini model, `key: configured (hidden)`, and `Gemini key and model access verified. No listing generated.` The command checks the usage table and makes only a model-metadata GET request; it does not generate text/images, save a product or spend a listing attempt. Actual photo generation must still be tested. If Shell is unavailable on your Render plan, include the checks in the deployment command after migrations.

Static collection must run during the build/deployment on Render; collecting into an unrelated shell instance is not a substitute for making those assets part of the running web service.

### 4. Test the live website

Sign in with an approved seller account. Open Add product (merchandise/groceries) or Add menu item (food). Select a product photo, add a factual note and choose Generate listing draft. Confirm the draft displays, review all suggestions, and choose Apply draft to form. Verify price and stock did not change. Save/submit only after confirming every field. Repeat with each selling segment you use. This is a real provider generation and counts toward that seller's daily allowance and Google API usage.

### 5. Test and distribute the mobile app

The mobile Seller Center → Catalog → Add product screen includes the same assistant for merchandise, groceries and food. The shared endpoint is deployed in step 3. No Gemini key or Google SDK belongs in the mobile application.

For Expo Go, run in a local terminal:

```powershell
cd mobile_app
npx expo start --go --lan
```

Open Expo Go on the same Wi-Fi, scan the current QR, sign in as an approved seller and open Seller Center → Catalog → Add product. Ensure `mobile_app/.env` has `EXPO_PUBLIC_API_URL=https://www.ziyamart.in/api/v1` if you want to test the live backend. Changing the backend provider alone does not require rebuilding an app that already contains the assistant; earlier installed versions without these screens need a new build.

To distribute an Android test APK:

```powershell
cd mobile_app
npx eas-cli build --platform android --profile preview
```

Install the resulting APK on your phone and repeat Generate → Review → Apply. The existing production profile targets the live API and creates a Play Store AAB:

```powershell
npx eas-cli build --platform android --profile production
```

Upload the finished AAB to your Play Console testing/release track through the normal release process. An EAS build alone does not publish an update to the store. iPhone distribution requires your normal Apple signing/TestFlight setup. No release build or store submission was performed by this implementation.

### 6. Troubleshooting

| Symptom | Check |
| --- | --- |
| Assistant missing | Verify the deployed Git commit, static build and template; reload the website. Install a recent app build or reload Expo. |
| Not configured | Add `GEMINI_API_KEY` to the Django web service and redeploy/restart it. |
| Model configuration needs updating | Replace an old OpenAI model value with `gemini-3.1-flash-lite`. |
| Gemini access needs checking | Run `check_listing_assistant --verify-provider`; check the key's project, restrictions, billing and model access. Provider HTTP 400/401/403/404 can indicate a key or model configuration issue. |
| Gemini service quota exhausted | Check Google AI Studio rate limits/usage and project billing. This differs from the seller's daily limit. |
| Daily limit reached | The account has used its allowance across website and app. It resets on the backend's local calendar day. |
| Usage table missing / database error | Deploy migration 0002 and run `python manage.py migrate --noinput` against the live database. |
| App fails but website works | Check the app API URL, seller token/session and app version; the assistant endpoint needs the same deployed backend. |
| Unusable draft | Retry with a clear product photo and a short factual note. No fields are applied automatically. |

Provider responses in automated tests are mocked. A real key, project quota and deployed backend are still required to confirm live output quality. Ordinary manual form entry remains available when the assistant cannot run. The platform's Google project pays for API use; sellers are not billed by an AI checkout in this version.

## Limits and data

Web: authenticated, CSRF-protected `POST /dashboard/seller/listing-assistant/`.
Mobile: authenticated `POST /api/v1/partners/seller/listing-assistant/`.
Both accept multipart `kind`, optional `notes`, and one to three repeated `photos` parts. Both share the same database quota, atomically incremented before each provider attempt. Provider failures also consume an attempt to bound repeated paid calls. Invalid files, disallowed roles and missing provider configuration consume no attempts. Other protected API throttles also apply to the mobile route.

Images must be JPEG/PNG/WebP, up to 8 MB and 20 megapixels each. Server-side decoding verifies real image data; resizing and re-encoding remove source metadata before transmission. Photos and notes are sent to Google Gemini only when Generate is selected. They are not saved to the application database by the assistant; only the seller, day and attempt count are stored. The backend sends inline image bytes to Gemini generateContent, without creating provider-hosted file uploads or saved conversations. Google's tier-specific data-use and retention policies still apply; this is not a zero-retention guarantee. No remote image URLs are accepted.

The previous Cloudflare copy/image tools, subscription purchase/confirmation routes, plan cards and Razorpay AI checkout are removed. Historical seller plan fields and purchase records remain for accounting; this change neither renews nor refunds them. Existing product photos are preserved.

## Validation

`python manage.py test dashboard.test_listing_assistant --settings=config.test_settings`

`cd mobile_app` then `npm run typecheck`, `npm test`, and `npx expo export --platform android --output-dir dist/listing-assistant-check`.

References: [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key), [Gemini image inputs](https://ai.google.dev/gemini-api/docs/image-understanding), [structured output](https://ai.google.dev/gemini-api/docs/structured-output), [model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite), [Render Django deployment](https://render.com/docs/deploy-django).
