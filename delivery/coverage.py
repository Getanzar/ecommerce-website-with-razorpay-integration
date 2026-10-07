"""Shared parcel routing and operations coverage policy."""
from .models import DeliveryAgentProfile, DeliveryZone


def has_local_coverage(pincode):
    # Offline approved riders still cover an area; jobs wait for them to go online.
    if DeliveryZone.objects.filter(pincode=pincode, is_active=False).exists():
        return False
    return DeliveryAgentProfile.objects.filter(
        pincode=pincode, status="approved", user__is_active=True,
    ).exists()


def seller_coverage_rows():
    from accounts.models import SellerProfile
    riders = {}
    for row in DeliveryAgentProfile.objects.filter(user__is_active=True).values("pincode", "status", "is_online"):
        counts = riders.setdefault(row["pincode"], {"approved": 0, "online": 0, "pending": 0})
        if row["status"] == "approved":
            counts["approved"] += 1
            counts["online"] += int(row["is_online"])
        elif row["status"] == "pending":
            counts["pending"] += 1
    disabled = set(DeliveryZone.objects.filter(is_active=False).values_list("pincode", flat=True))
    rows = []
    for seller in SellerProfile.objects.select_related("user").order_by("business_pincode", "store_name"):
        counts = riders.get(seller.business_pincode, {"approved": 0, "online": 0, "pending": 0})
        covered = bool(counts["approved"] and seller.business_pincode not in disabled)
        rows.append({"seller": seller, **counts, "covered": covered,
                     "zone_disabled": seller.business_pincode in disabled,
                     "gps_ready": seller.business_latitude is not None and seller.business_longitude is not None})
    return rows
