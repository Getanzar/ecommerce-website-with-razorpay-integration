# Google sign-in setup for ZIYAMART

Email-and-password signup and email/username login work independently of Google configuration. Google sign-in requires a Google Cloud OAuth web client. Keep the client secret in your hosting environment; never commit it or send it in chat.

## 1. Create the Google client

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select or create the project that owns ZIYAMART.
2. In **Google Auth Platform**, configure Branding, Audience, and Data Access. Set the app name to ZIYAMART, provide your support email and website information, and request only `openid`, `email`, and `profile`. If the app is in Testing, add the Google accounts that will test it. Publish the app when ready for public users, following Google's console requirements.
3. Under **Clients**, create an OAuth client with application type **Web application**.
4. Add the exact **Authorized redirect URI** for your website. Your live website redirects to `https://www.ziyamart.in`; use:

   `https://www.ziyamart.in/accounts/google/callback/`

   For another hosting environment, replace the hostname with that exact domain. Scheme, hostname, path and trailing slash must match. Register each separate environment if you use multiple domains. This implementation uses a server redirect, so it does not require embedding the client secret in JavaScript.
5. Copy the client ID and client secret to your hosting environment, not the repository.

## 2. Configure hosting

Set these environment variables in your hosting provider's Environment settings:

```dotenv
GOOGLE_OAUTH_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=https://www.ziyamart.in/accounts/google/callback/
```

Use your actual canonical website domain. Save the environment settings and restart/redeploy the application. For local development you can register `http://localhost:8000/accounts/google/callback/` and set the redirect variable to that value. Do not use a local callback in production.

Deployment must install `requirements.txt` and run `python manage.py migrate --noinput` to create the Google-account identity table. The repository's Procfile already runs migrations at web-process startup.

## 3. Check the flow

- Open `/accounts/signup/` and choose **Continue with Google**.
- A new Google customer should land on **My Profile**, signed in, with their email verified and no separate ZIYAMART password required.
- Sign out, then sign in with Google again. The same customer account should open.
- Existing email/password customers first sign in normally, open **Personal Information**, and connect Google with the same verified email. This avoids creating duplicate accounts or silently linking an account by email alone.
- Cancel Google consent and confirm you return to login without a new account.
- If Google reports `redirect_uri_mismatch`, compare the callback variable with the Google client's Authorized redirect URI character for character.
- Without credentials, the button returns a clear message that Google sign-in is not available yet; it does not simulate a successful login.

The implementation uses Google's authorization-code flow, state, nonce, PKCE, and Google's official Python library to verify signed ID tokens, issuer, audience and expiry. Google subject IDs identify returning accounts even after a primary-email update. Access and refresh tokens are not retained.

Primary references: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect), [Google ID token verification](https://googleapis.dev/python/google-auth/latest/reference/google.oauth2.id_token.html).
