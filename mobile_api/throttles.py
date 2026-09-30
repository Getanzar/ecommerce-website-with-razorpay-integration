"""Limits for public authentication endpoints; use a shared cache in production."""
import hashlib
from collections.abc import Mapping

from django.contrib.auth.models import User
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class AuthIPThrottle(SimpleRateThrottle):
    scope = "mobile_auth_ip"
    rate = "30/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class AuthAccountThrottle(SimpleRateThrottle):
    scope = "mobile_auth_account"
    rate = "10/min"

    def get_cache_key(self, request, view):
        identity = str(request.data.get("email") or request.data.get("identity") or "").strip().lower()
        if "@" not in identity and identity:
            # Username and email logins share an account limit.
            identity = User.objects.filter(username__iexact=identity).values_list("email", flat=True).first() or identity
        digest = hashlib.sha256(identity.lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class EmailCooldownThrottle(AuthAccountThrottle):
    scope = "mobile_auth_email_cooldown"
    rate = "1/min"


class EmailHourlyThrottle(AuthAccountThrottle):
    scope = "mobile_auth_email_hour"
    rate = "5/hour"


class EmailIPThrottle(AuthIPThrottle):
    scope = "mobile_auth_email_ip"
    rate = "20/hour"


class PublicAuthView(APIView):
    throttle_classes = [AuthIPThrottle, AuthAccountThrottle]

    def initial(self, request, *args, **kwargs):
        if not isinstance(request.data, Mapping):
            raise ValidationError({"message": "Send a JSON object with the required fields."})
        super().initial(request, *args, **kwargs)


class EmailAuthView(PublicAuthView):
    throttle_classes = [AuthIPThrottle, EmailIPThrottle, EmailHourlyThrottle, EmailCooldownThrottle]
