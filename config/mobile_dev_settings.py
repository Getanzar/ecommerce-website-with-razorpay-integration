"""LAN-only mobile development settings using the website's live services.

This keeps PostgreSQL, Cloudinary, Brevo, and Razorpay configuration from the
normal settings module while allowing Expo Go to reach Django over local HTTP.
Never use this settings module for a public deployment.
"""

import socket

from .settings import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
# Wi-Fi and hotspot addresses can change between development sessions.
try:
    ALLOWED_HOSTS += sorted({
        address[4][0]
        for address in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    } - set(ALLOWED_HOSTS))
except socket.gaierror:
    # Keep localhost usable even when the machine's hostname cannot resolve.
    pass
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
MOBILE_API_DEBUG_OTP = False
