from .settings import *  # noqa: F403


DEBUG = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / ".ui_review.sqlite3",  # noqa: F405
    }
}
ALLOWED_HOSTS = ["127.0.0.1", "127.0.0.2", "localhost", "192.168.31.121"]
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MOBILE_API_DEBUG_OTP = True
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
