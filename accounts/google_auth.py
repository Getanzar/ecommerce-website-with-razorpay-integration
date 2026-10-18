"""Google OpenID Connect authorization-code flow for website accounts."""
import base64
import hashlib
import secrets
from functools import partial
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower, Trim
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_GET, require_POST
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token

from .identity import generate_username
from .models import GoogleAccount

BACKEND = "accounts.backends.EmailOrUsernameBackend"


@require_POST
@never_cache
def google_start(request):
    return _start_google(request)


def _start_google(request):
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        messages.error(request, "Google sign-in is not available yet. Please use email to continue.")
        return redirect("profile_detail" if request.user.is_authenticated else "login")
    state, nonce, verifier = (secrets.token_urlsafe(40) for _ in range(3))
    callback = settings.GOOGLE_OAUTH_REDIRECT_URI or request.build_absolute_uri(reverse("google_callback"))
    request.session["google_oauth"] = {
        "state": state, "nonce": nonce, "verifier": verifier, "callback": callback,
        "started_at": timezone.now().timestamp(),
        "user_id": request.user.pk if request.user.is_authenticated else None,
    }
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": callback,
        "response_type": "code", "scope": "openid email profile",
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account",
    }))


def _google_user(claims, current_user):
    """Link only explicitly, and use Google's stable subject on later logins."""
    subject, email = claims["sub"], claims["email"].strip().lower()
    with transaction.atomic():
        account = GoogleAccount.objects.select_related("user").filter(subject=subject).first()
        if account:
            if current_user.is_authenticated and account.user_id != current_user.pk:
                raise ValueError("This Google account is already connected to another account.")
            if not account.user.is_active:
                raise ValueError("This account is unavailable. Please contact support.")
            return account.user
        if current_user.is_authenticated:
            if email != current_user.email.strip().lower() or not current_user.profile.email_verified:
                raise ValueError("Connect a Google account with the same verified email as your profile.")
            if GoogleAccount.objects.filter(user=current_user).exists():
                raise ValueError("Your profile already has a different Google account connected.")
            user = current_user
        else:
            if User.objects.annotate(identity=Lower(Trim("email"))).filter(identity=email).exists():
                raise ValueError("An account already uses this email. Sign in to your existing account, then connect Google from Personal Information.")
            user = User.objects.create_user(
                username=generate_username(), email=email, password=None,
                first_name=str(claims.get("given_name", ""))[:150],
                last_name=str(claims.get("family_name", ""))[:150], is_active=True,
            )
            user.profile.email_verified = True
            user.profile.save(update_fields=["email_verified"])
        GoogleAccount.objects.create(user=user, subject=subject)
        return user


@require_GET
@never_cache
@sensitive_variables("tokens", "claims", "code", "flow")
def google_callback(request):
    flow = request.session.pop("google_oauth", None)
    error_route = "profile_detail" if request.user.is_authenticated else "login"
    if not flow or not constant_time_compare(str(flow.get("state", "")), request.GET.get("state", "")) or timezone.now().timestamp() - flow.get("started_at", 0) > 600:
        messages.error(request, "Your Google sign-in session expired or could not be verified. Please try again.")
        return redirect(error_route)
    if flow.get("mobile"):
        from django.contrib.auth.models import AnonymousUser
        request.user = User.objects.filter(pk=flow["user_id"], is_active=True).first() if flow.get("user_id") else AnonymousUser()
        if request.user is None:
            from mobile_api.customer_parity import google_mobile_result
            return google_mobile_result(flow, error="This account is unavailable.")
    current_user_id = request.user.pk if request.user.is_authenticated else None
    if current_user_id != flow.get("user_id"):
        messages.error(request, "Your account session changed. Please start Google sign-in again.")
        return redirect(error_route)
    code = request.GET.get("code", "")
    if request.GET.get("error") or not code:
        if flow.get("mobile"):
            from mobile_api.customer_parity import google_mobile_result
            return google_mobile_result(flow, error="Google sign-in was cancelled. Please try again.")
        messages.info(request, "Google sign-in was not completed. You can try again or continue with email.")
        return redirect(error_route)
    try:
        response = requests.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": flow["callback"], "grant_type": "authorization_code",
            "code_verifier": flow["verifier"],
        }, timeout=10, allow_redirects=False)
        response.raise_for_status()
        tokens = response.json()
        claims = verify_oauth2_token(tokens["id_token"], partial(GoogleRequest(), timeout=10), settings.GOOGLE_OAUTH_CLIENT_ID)
        if not claims.get("sub") or len(str(claims["sub"])) > 255 or claims.get("email_verified") is not True:
            raise ValueError("Google could not verify this email address.")
        if not constant_time_compare(str(claims.get("nonce", "")), flow["nonce"]):
            raise ValueError("Your Google sign-in could not be verified. Please try again.")
        if claims.get("azp", settings.GOOGLE_OAUTH_CLIENT_ID) != settings.GOOGLE_OAUTH_CLIENT_ID:
            raise ValueError("Your Google sign-in could not be verified. Please try again.")
        validate_email(claims.get("email", ""))
        if len(claims["email"]) > 254:
            raise ValueError("Your Google email address is too long.")
        user = _google_user(claims, request.user)
    except (requests.RequestException, GoogleAuthError, KeyError, TypeError, ValidationError, IntegrityError):
        if flow.get("mobile"):
            from mobile_api.customer_parity import google_mobile_result
            return google_mobile_result(flow, error="We couldn't complete Google sign-in. Please try again.")
        messages.error(request, "We couldn't complete Google sign-in. Please try again or use email.")
        return redirect(error_route)
    except ValueError as exc:
        # Never surface provider responses or raw token-decoding errors.
        safe_errors = {
            "This Google account is already connected to another account.",
            "This account is unavailable. Please contact support.",
            "Connect a Google account with the same verified email as your profile.",
            "Your profile already has a different Google account connected.",
            "An account already uses this email. Sign in to your existing account, then connect Google from Personal Information.",
        }
        if flow.get("mobile"):
            from mobile_api.customer_parity import google_mobile_result
            return google_mobile_result(flow, error=str(exc) if str(exc) in safe_errors else "We couldn't verify Google sign-in. Please try again.")
        messages.error(request, str(exc) if str(exc) in safe_errors else "We couldn't verify Google sign-in. Please try again or use email.")
        return redirect(error_route)
    if flow.get("mobile"):
        from mobile_api.customer_parity import google_mobile_result
        return google_mobile_result(flow, user=user)
    login(request, user, backend=BACKEND)
    request.session.pop("pending_verification_email", None)
    messages.success(request, "You're signed in with Google. You can update your profile whenever you're ready.")
    return redirect(request.session.pop("seller_signup_next", "profile_detail"))
