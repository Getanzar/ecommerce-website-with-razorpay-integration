"""Mobile account verification, Google handoff and delivery-interest endpoints."""
import base64
import hashlib
import re
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.identity import duplicate_identifiers
from accounts.utils import send_profile_email_otp
from .serializers import UserSerializer
from .throttles import AuthIPThrottle, EmailAuthView, PublicAuthView


class ProfileEmailRequest(EmailAuthView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = serializers.EmailField(max_length=254).run_validation(request.data.get("email", "")).lower()
        if email == request.user.email.lower():
            return Response({"message": "This is already your account email."}, status=400)
        if duplicate_identifiers("", email, "", exclude_user_id=request.user.pk):
            return Response({"message": "This email is already registered to another account."}, status=400)
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        if not send_profile_email_otp(email, code):
            return Response({"message": "We couldn't send a verification code. Please try again."}, status=503)
        cache.set(f"mobile-email:{request.user.pk}", {"email": email, "hash": make_password(code), "attempts": 0, "expires": timezone.now().timestamp() + 600}, 600)
        return Response({"message": "Enter the code sent to your new email.", "email": email})


class ProfileEmailVerify(PublicAuthView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        key = f"mobile-email:{request.user.pk}"
        lock = key + ":lock"
        if not cache.add(lock, True, 15):
            return Response({"message": "Please wait before trying again."}, status=429)
        try:
            pending = cache.get(key)
            if not pending or pending["attempts"] >= 5 or pending["expires"] <= timezone.now().timestamp():
                cache.delete(key)
                return Response({"message": "Code expired. Request another code."}, status=400)
            if not check_password(str(request.data.get("otp", "")).strip(), pending["hash"]):
                pending["attempts"] += 1
                # Attempts never extend the original verification deadline.
                pending.setdefault("expires", timezone.now().timestamp() + 600)
                cache.set(key, pending, max(1, int(pending["expires"] - timezone.now().timestamp())))
                return Response({"message": "Incorrect verification code."}, status=400)
            if duplicate_identifiers("", pending["email"], "", exclude_user_id=request.user.pk):
                cache.delete(key)
                return Response({"message": "This email is already registered."}, status=400)
            with transaction.atomic():
                request.user.email = pending["email"]
                request.user.save(update_fields=["email"])
                request.user.profile.email_verified = True
                request.user.profile.save(update_fields=["email_verified"])
            cache.delete(key)
            return Response(UserSerializer(request.user, context={"request": request}).data)
        except IntegrityError:
            return Response({"message": "This email is already registered."}, status=400)
        finally:
            cache.delete(lock)


class GoogleMobileStart(PublicAuthView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
            return Response({"message": "Google sign-in is unavailable. Please continue with email."}, status=503)
        challenge = str(request.data.get("challenge", ""))
        state = str(request.data.get("state", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state):
            return Response({"message": "Invalid sign-in request."}, status=400)
        ticket = secrets.token_urlsafe(32)
        cache.set("mobile-google-start:" + ticket, {"challenge": challenge, "state": state, "user_id": request.user.pk if request.user.is_authenticated else None}, 120)
        url = request.build_absolute_uri(reverse("mobile-google-browser")) + "?" + urlencode({"ticket": ticket})
        return Response({"url": url})


@require_GET
@never_cache
def google_browser(request):
    from accounts.google_auth import _start_google
    ticket = request.GET.get("ticket", "")
    key = "mobile-google-start:" + ticket
    flow = cache.get(key) if len(ticket) <= 100 else None
    if not flow or not cache.add(key + ":used", True, 120):
        return HttpResponseBadRequest("This sign-in link expired. Please return to the app and try again.")
    cache.delete(key)
    # Browser cookies must never silently connect the app to another account.
    request.user = User.objects.filter(pk=flow["user_id"], is_active=True).first() if flow["user_id"] else AnonymousUser()
    if request.user is None:
        return HttpResponseBadRequest("This account is unavailable.")
    response = _start_google(request)
    if "google_oauth" in request.session:
        request.session["google_oauth"] = {**request.session["google_oauth"], "mobile": flow}
    return response


def google_mobile_result(flow, user=None, error=""):
    mobile = flow["mobile"]
    params = {"state": mobile["state"]}
    if error:
        params["error"] = error
    else:
        code = secrets.token_urlsafe(32)
        cache.set("mobile-google-code:" + code, {"user_id": user.pk, "challenge": mobile["challenge"], "link_user_id": mobile["user_id"]}, 60)
        params["code"] = code
    # Fixed destination: no caller-controlled redirect URLs or tokens in links.
    from django.http import HttpResponseRedirect
    class AppRedirect(HttpResponseRedirect):
        allowed_schemes = ["ziyamart"]
    return AppRedirect("ziyamart://auth/callback?" + urlencode(params))


class GoogleMobileExchange(PublicAuthView):
    permission_classes = [AllowAny]

    def post(self, request):
        from .views import auth_payload
        code, verifier = str(request.data.get("code", "")), str(request.data.get("verifier", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", verifier) or len(code) > 100:
            return Response({"message": "Invalid sign-in request."}, status=400)
        key = "mobile-google-code:" + code
        flow = cache.get(key)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if not flow or not secrets.compare_digest(flow["challenge"], challenge):
            return Response({"message": "Sign-in expired. Please try again."}, status=400)
        if flow.get("link_user_id") and (not request.user.is_authenticated or request.user.pk != flow["link_user_id"]):
            return Response({"message": "Sign in again before connecting Google."}, status=403)
        if not cache.add(key + ":used", True, 120):
            return Response({"message": "Sign-in expired. Please try again."}, status=400)
        cache.delete(key)
        user = User.objects.filter(pk=flow["user_id"], is_active=True).first()
        if not user:
            return Response({"message": "This account is unavailable."}, status=400)
        if flow.get("link_user_id"):
            return Response({"linked": True, "user": UserSerializer(user, context={"request": request}).data})
        return Response(auth_payload(user, str(request.data.get("device_name", "Mobile device"))[:100]))


class DeliveryInterest(PublicAuthView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthIPThrottle]

    def post(self, request):
        from food.forms import FoodDeliveryAreaRequestForm
        service = str(request.data.get("service", "food"))
        if service not in {"food", "grocery"}:
            return Response({"message": "Choose food or grocery delivery."}, status=400)
        form = FoodDeliveryAreaRequestForm(request.data)
        if not form.is_valid():
            return Response({"message": "Check your pincode and comment.", "errors": dict(form.errors)}, status=400)
        identity = str(request.user.pk) if request.user.is_authenticated else self.get_client_ip(request)
        key = "mobile-area-interest:" + hashlib.sha256(identity.encode()).hexdigest()
        if not cache.add(key, True, 60):
            return Response({"message": "Your request was recently received. Please wait a minute."}, status=429)
        row = form.save(commit=False)
        row.service = service
        if request.user.is_authenticated:
            row.user = request.user
        row.save()
        return Response({"message": "Thank you for your interest. Your neighbourhood will help us plan where to deliver next."}, status=201)

    @staticmethod
    def get_client_ip(request):
        return request.META.get("REMOTE_ADDR", "unknown")
