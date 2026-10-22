import json

import requests
from django.conf import settings
from django.db import transaction


def manifest_delhivery_charge(order, charge):
    """Manifest one seller package and retain the complete provider response."""
    charge = type(charge).objects.get(pk=charge.pk)
    if charge.awb_number:
        return charge
    if charge.carrier_status in {"manifestation_failed", "manifestation_pending"}:
        return charge
    if order.status in {"Cancelled", "Returned"} or (order.payment_method != "cod" and order.payment_status != "Paid"):
        return charge
    seller = charge.seller
    pickup_name = seller.delhivery_pickup_name if seller else settings.DELHIVERY_PICKUP_LOCATION
    if not settings.DELHIVERY_API_KEY:
        charge.carrier_status = "quote_only"
        charge.save(update_fields=["carrier_status"])
        return charge
    from .pickups import ensure_seller_warehouse, validate_destination
    try:
        validate_destination(order)
        if seller:
            pickup_name = ensure_seller_warehouse(seller)
        if not pickup_name:
            raise ValueError("No registered pickup location is configured.")
        if seller and seller.business_pincode != charge.origin_pincode:
            raise ValueError("Seller pickup address changed since checkout. Support must review the shipping quote before booking.")
    except (requests.RequestException, ValueError, TypeError) as exc:
        charge.pickup_error = str(exc)[:1000]
        charge.carrier_status = "pickup_registration_required"
        charge.save(update_fields=["pickup_error", "carrier_status"])
        return charge
    with transaction.atomic():
        charge = type(charge).objects.select_for_update().get(pk=charge.pk)
        if charge.awb_number or charge.carrier_status in {"manifestation_failed", "manifestation_pending"}:
            return charge
        charge.pickup_location_name = pickup_name
        charge.carrier_status = "manifestation_pending"
        charge.pickup_error = ""
        charge.save(update_fields=["pickup_location_name", "carrier_status", "pickup_error"])
    items = order.items.filter(product__seller=seller)
    description = ", ".join(f"{item.product_name} x{item.quantity}" for item in items)[:250]
    shipment = {
        "name": order.full_name,
        "add": order.address,
        "pin": order.pincode,
        "city": order.city,
        "state": order.state,
        "country": "India",
        "phone": order.phone,
        "order": f"{order.pk}-{seller.pk if seller else 'platform'}",
        "payment_mode": "COD" if order.payment_method == "cod" else "Pre-paid",
        "cod_amount": float(charge.customer_collection_amount) if order.payment_method == "cod" else 0,
        "total_amount": float(charge.customer_collection_amount),
        "products_desc": description or "Marketplace order",
        "shipping_mode": "Surface",
        "weight": charge.chargeable_weight_grams,
        "seller_name": seller.store_name if seller else "ZIYAMART",
        "seller_add": seller.business_address if seller else settings.DELHIVERY_PICKUP_LOCATION,
        "seller_inv": f"ZIYA-{order.pk}-{seller.pk if seller else 'platform'}",
    }
    try:
        response = requests.post(
            "https://track.delhivery.com/api/cmu/create.json",
            headers={"Authorization": f"Token {settings.DELHIVERY_API_KEY}"},
            data={"format": "json", "data": json.dumps({"pickup_location": {"name": pickup_name}, "shipments": [shipment]})},
            timeout=30,
        )
        response.raise_for_status()
        provider = response.json()
        charge.manifestation_payload = provider
        package = (provider.get("packages") or [{}])[0]
        charge.awb_number = str(package.get("waybill") or package.get("wb") or "")
        charge.carrier_status = "manifested" if charge.awb_number else "manifestation_pending"
        charge.pickup_error = "" if charge.awb_number else "Shipment booking needs carrier review before pickup can be scheduled."
    except (requests.RequestException, ValueError, TypeError) as exc:
        charge.manifestation_payload = {"error": str(exc)[:500]}
        charge.carrier_status = "manifestation_failed"
        charge.pickup_error = "Shipment booking response needs carrier review before pickup can be scheduled."
    charge.save(update_fields=["manifestation_payload", "awb_number", "carrier_status", "pickup_error"])
    return charge


def manifest_delhivery_shipments(order, charges):
    manifested = [
        manifest_delhivery_charge(order, charge)
        for charge in charges
        if charge.provider == "delhivery"
    ]
    if order.payment_method == "cod":
        from payments.models import CODRemittance

        for charge in manifested:
            CODRemittance.objects.get_or_create(
                parcel_order=order,
                seller=charge.seller,
                defaults={
                    "source": "delhivery",
                    "amount": charge.customer_collection_amount,
                    "status": "awaiting_collection",
                },
            )
    return manifested
