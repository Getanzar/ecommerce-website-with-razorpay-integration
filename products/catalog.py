from django.db.models import Prefetch, Q

from .models import Product, ProductVariant


def public_products(queryset=None):
    """Products that may be exposed on a customer-facing surface."""
    queryset = queryset if queryset is not None else Product.objects.all()
    return queryset.filter(
        is_active=True,
        moderation_status=Product.MODERATION_APPROVED,
    ).filter(
        Q(seller__isnull=True) | Q(seller__status="approved")
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
        Q(product__seller__isnull=True) | Q(product__seller__status="approved")
    )


def with_storefront_variants(queryset):
    """Prefetch the variants used to calculate public starting prices."""
    return queryset.prefetch_related(Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True, stock__gt=0).select_related("color"),
        to_attr="storefront_variants",
    ))
