"""LAN-only mobile development settings using the website's live services.

This keeps PostgreSQL, Cloudinary, Brevo, and Razorpay configuration from the
normal settings module while allowing Expo Go to reach Django over local HTTP.
Never use this settings module for a public deployment.
"""

from .settings import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "10.153.184.95"]
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
MOBILE_API_DEBUG_OTP = False
