from pathlib import Path
import os
from email.utils import parseaddr
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# Payment gateways
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

# Seller AI listing tools. These credentials are server-side only and must
# never be rendered into HTML or sent to the browser.
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_TEXT_MODEL = os.getenv(
    "CLOUDFLARE_TEXT_MODEL", "@cf/meta/llama-3.1-8b-instruct-fp8-fast"
)
CLOUDFLARE_VISION_MODEL = os.getenv(
    "CLOUDFLARE_VISION_MODEL", "@cf/meta/llama-3.2-11b-vision-instruct"
)
CLOUDFLARE_IMAGE_MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b"
)

# Monthly seller image plans. While a plan is active, text listing generation
# is included without a per-generation charge.
SELLER_AI_PLANS = {
    "starter": {"name": "Starter", "price_paise": 9900, "image_limit": 25},
    "growth": {"name": "Growth", "price_paise": 49900, "image_limit": 150},
    "pro": {"name": "Pro", "price_paise": 99900, "image_limit": 400},
}

# 🔑 Delhivery API Key
DELHIVERY_API_KEY = os.getenv("DELHIVERY_API_KEY")

# Brevo Email API
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "ZIYAMART")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL") or parseaddr(
    os.getenv("DEFAULT_FROM_EMAIL", "") or os.getenv("EMAIL_HOST_USER", "")
)[1]
BREVO_API_TIMEOUT = int(os.getenv("BREVO_API_TIMEOUT", "15"))

SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    'ziyamart.in',
    'www.ziyamart.in',
    'ecommerce-website-with-razorpay.onrender.com',  # add this
]

CSRF_TRUSTED_ORIGINS = [
    "https://ziyamart.in",
    "https://www.ziyamart.in",
    "https://ecommerce-website-with-razorpay.onrender.com",  # add this
]


INSTALLED_APPS = [
    # Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third Party
    'rest_framework',
    'cloudinary',
    'cloudinary_storage',

    # Local Apps
    'products',
    'orders',
    'accounts',
    'cart.apps.CartConfig',
    'dashboard',
    'addresses',
    'food',
    'groceries',
    'delivery',
    'payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                
                'products.context_processors.categories_processor',
                'products.context_processors.commerce_carts_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv("DB_NAME"),
        'USER': os.getenv("DB_USER"),
        'PASSWORD': os.getenv("DB_PASSWORD"),
        'HOST': os.getenv("DB_HOST"),
        'PORT': os.getenv("DB_PORT", "5432"),
    }
}

# Only require SSL for Neon/production
if os.getenv("DB_HOST") and "neon.tech" in os.getenv("DB_HOST"):
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": "require",
    }


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# DRF (optional)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
}

# Stripe (optional checkout)
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY', 'pk_test_xxx')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', 'sk_test_xxx')

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/accounts/login/'

DELHIVERY_PICKUP_LOCATION = "ziyamart garments bazaar wilson gunj pathantola road, sahaswan, budaun, uttar-pradesh, 243638"
DELHIVERY_ORIGIN_PINCODE = os.getenv("DELHIVERY_ORIGIN_PINCODE", "243638")
DELHIVERY_RATE_URL = os.getenv(
    "DELHIVERY_RATE_URL",
    "https://track.delhivery.com/api/kinko/v1/invoice/charges/.json",
)
DELHIVERY_RATE_TIMEOUT = int(os.getenv("DELHIVERY_RATE_TIMEOUT", "15"))
DELHIVERY_REQUIRE_LIVE_QUOTE = os.getenv("DELHIVERY_REQUIRE_LIVE_QUOTE", "False").lower() in {"1", "true", "yes", "on"}
DELHIVERY_FALLBACK_BASE = os.getenv("DELHIVERY_FALLBACK_BASE", "60.00")
DELHIVERY_FALLBACK_PER_500G = os.getenv("DELHIVERY_FALLBACK_PER_500G", "25.00")
DELHIVERY_HANDLING_FEE = os.getenv("DELHIVERY_HANDLING_FEE", "5.00")

# Immutable checkout-tax configuration. Local delivery itself is intentionally
# untaxed per the marketplace policy; merchandise and platform services remain
# separate invoice components.
PLATFORM_FEE_GST_PERCENT = os.getenv("PLATFORM_FEE_GST_PERCENT", "18.00")
RETURN_WINDOW_DAYS = int(os.getenv("RETURN_WINDOW_DAYS", "7"))
RESTAURANT_GST_PERCENT = os.getenv("RESTAURANT_GST_PERCENT", "5.00")
ECOMMERCE_TCS_PERCENT = os.getenv("ECOMMERCE_TCS_PERCENT", "0.50")
DELHIVERY_GST_PERCENT = os.getenv("DELHIVERY_GST_PERCENT", "18.00")
LOCAL_DELIVERY_BASE_FEE = os.getenv("LOCAL_DELIVERY_BASE_FEE", "30.00")
LOCAL_DELIVERY_INCLUDED_KM = os.getenv("LOCAL_DELIVERY_INCLUDED_KM", "2.00")
LOCAL_DELIVERY_PER_KM = os.getenv("LOCAL_DELIVERY_PER_KM", "8.00")
DELIVERY_AGENT_PLATFORM_FEE_PERCENT = os.getenv("DELIVERY_AGENT_PLATFORM_FEE_PERCENT", "10.00")

# Seller payouts (RazorpayX). Keep separate from customer checkout credentials.
RAZORPAYX_KEY_ID = os.getenv("RAZORPAYX_KEY_ID", "")
RAZORPAYX_KEY_SECRET = os.getenv("RAZORPAYX_KEY_SECRET", "")
RAZORPAYX_ACCOUNT_NUMBER = os.getenv("RAZORPAYX_ACCOUNT_NUMBER", "")
SELLER_PAYOUT_MODE = os.getenv("SELLER_PAYOUT_MODE", "IMPS")
RAZORPAYX_WEBHOOK_SECRET = os.getenv("RAZORPAYX_WEBHOOK_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# Transactional email is sent through the Brevo HTTP API in config.email.
DEFAULT_FROM_EMAIL = BREVO_SENDER_EMAIL

# =====================================
# Security settings for Render (HTTPS)
# =====================================

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG and os.getenv(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", "True"
).lower() in {"1", "true", "yes", "on"}
SECURE_HSTS_PRELOAD = not DEBUG and os.getenv(
    "SECURE_HSTS_PRELOAD", "True"
).lower() in {"1", "true", "yes", "on"}

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
