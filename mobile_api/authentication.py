import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import DeviceSession


def issue_session(user, device_name="Mobile device"):
    raw = "zm_" + secrets.token_urlsafe(32)
    DeviceSession.objects.create(user=user, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                                 device_name=str(device_name)[:120], expires_at=timezone.now() + timedelta(days=30))
    return raw


class DeviceAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        # Existing installs retain their legacy token until their next login.
        if not key.startswith("zm_"):
            return super().authenticate_credentials(key)
        session = DeviceSession.objects.select_related("user").filter(
            token_hash=hashlib.sha256(key.encode()).hexdigest(), revoked_at__isnull=True,
            expires_at__gt=timezone.now(), user__is_active=True).first()
        if not session:
            raise AuthenticationFailed("This device session has expired or was revoked.")
        DeviceSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now())
        return session.user, session
