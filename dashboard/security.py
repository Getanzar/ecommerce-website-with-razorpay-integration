from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import AdminAuditLog


def can_access_operations(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or (user.is_staff and user.has_perm("dashboard.access_operations_dashboard")))
    )


def operations_admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), "/admin/login/")
        if not can_access_operations(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def audit(request, action, entity, summary, **metadata):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    ip = forwarded or request.META.get("REMOTE_ADDR") or None
    return AdminAuditLog.objects.create(
        actor=request.user,
        action=action,
        entity_type=entity.__class__.__name__ if not isinstance(entity, str) else entity,
        entity_id=str(getattr(entity, "pk", "")),
        summary=summary,
        metadata=metadata,
        ip_address=ip,
    )
