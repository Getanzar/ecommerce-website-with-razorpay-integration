from django.conf import settings
from django.core.checks import Warning, register, Tags


@register(Tags.security, deploy=True)
def shared_auth_cache(app_configs, **kwargs):
    backend = settings.CACHES["default"]["BACKEND"]
    if backend.endswith(("LocMemCache", "DummyCache")):
        return [Warning(
            "Authentication rate limits need a shared production cache.",
            hint="Set DJANGO_CACHE_TABLE=ziyamart_cache and run manage.py createcachetable before starting workers, or configure a shared cache backend.",
            id="mobile_api.W001",
        )]
    return []
