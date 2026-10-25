"""Shared, bounded limits for browser authentication, including admin login."""
import hashlib

from django.core.cache import cache
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class BrowserAuthRateLimitMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST":
            return None
        match = request.resolver_match
        if not match:
            return None
        login = match.view_name in {"login", "admin:login"}
        email_action = match.url_name in {"signup", "password_reset", "password_reset_resend", "resend_signup_otp", "forgot_username"}
        if not login and not (email_action and request.path.startswith("/accounts/")):
            return None
        action = "login" if login else "email"
        raw_identity = (request.POST.get("username") or request.POST.get("email")) if login else request.POST.get("email")
        identity = str(raw_identity or "").strip().casefold()
        # Use the actual peer address. Never trust an arbitrary forwarded header.
        buckets = [("ip", request.META.get("REMOTE_ADDR", "unknown"), 30 if login else 20)]
        if identity:
            buckets.append(("identity", identity, 10 if login else 5))
        blocked = False
        for scope, value, limit in buckets:
            digest = hashlib.sha256(value.encode()).hexdigest()
            key = f"browser-auth:{action}:{scope}:{digest}"
            if cache.add(key, 1, timeout=60):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:  # The one-minute bucket expired between calls.
                    cache.add(key, 1, timeout=60)
                    count = 1
            blocked |= count > limit
        if blocked:
            response = HttpResponse("Too many attempts. Please wait one minute and try again.", status=429)
            response["Retry-After"] = "60"
            response["Cache-Control"] = "no-store"
            return response
        return None
