from django.db.models import Prefetch, Q

from .models import Product, ProductVariant


def _approved_seller_condition(prefix):
    registered = Q(**{prefix + "registration_type": "registered"})
    small = Q(**{
        prefix + "registration_type": "small", prefix + "business_segment": "shop",
        prefix + "gstin": "", prefix + "identity_status": "verified",
        prefix + "small_seller_declaration": True,
        prefix + "aadhaar_consent_at__isnull": False,
        prefix + "identity_verified_at__isnull": False,
        prefix + "identity_verified_by__isnull": False,
        prefix + "business_latitude__isnull": False,
        prefix + "business_longitude__isnull": False,
        prefix + "business_gps_verified_at__isnull": False,
    }) & ~Q(**{prefix + "identity_review_reference": ""})
    for name in ("aadhaar_last4", "legal_business_name", "business_category", "business_pincode", "bank_account_holder", "bank_account_last4", "bank_ifsc_code"):
        small &= ~Q(**{prefix + name: ""})
    return Q(**{prefix + "status": "approved"}) & (registered | small)


def public_products(queryset=None):
    """Products that may be exposed on a customer-facing surface."""
    queryset = queryset if queryset is not None else Product.objects.all()
    return queryset.filter(
        is_active=True,
        moderation_status=Product.MODERATION_APPROVED,
    ).filter(
        Q(seller__isnull=True) | _approved_seller_condition("seller__")
    )


def in_stock_products(queryset=None):
    """Public products with at least one active, in-stock variant."""
    return public_products(queryset).filter(
        variants__is_active=True,
        variants__stock__gt=0,
    ).distinct()


def sellable_variants(queryset=None):
    """Variants that are safe to add to a cart or finalize in an order."""
    queryset = queryset if queryset is not None else ProductVariant.objects.all()
    return queryset.filter(
        is_active=True,
        stock__gt=0,
        product__is_active=True,
        product__moderation_status=Product.MODERATION_APPROVED,
    ).filter(
        Q(product__seller__isnull=True) | _approved_seller_condition("product__seller__")
    )


def with_storefront_variants(queryset):
    """Prefetch the variants used to calculate public starting prices."""
    return queryset.prefetch_related(Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True, stock__gt=0).select_related("color"),
        to_attr="storefront_variants",
    ))
