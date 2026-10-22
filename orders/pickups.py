"""Persist carrier attempts before sending requests; ambiguous outcomes require review."""
import hashlib
import json
import logging
from datetime import datetime, time, timedelta

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from payments.models import DelhiveryPickupRequest, DelhiveryWarehouseRegistration, SellerDeliveryCharge

logger = logging.getLogger(__name__)
ACTIVE_PICKUPS = ("requesting", "scheduled", "auto_pickup", "review")
COLLECTED_STATUSES = {"in transit", "dispatched", "out for delivery", "delivered", "in transit rto", "returned rto"}


class PickupSetupError(ValueError):
    pass


def _headers():
    if not settings.DELHIVERY_API_KEY:
        raise PickupSetupError("Delhivery access is not configured. Contact marketplace support.")
    return {"Authorization": f"Token {settings.DELHIVERY_API_KEY}"}


def _pin_details(pincode):
    response = requests.get(
        "https://track.delhivery.com/c/api/pin-codes/json/",
        params={"pin": pincode}, headers=_headers(), timeout=10,
    )
    response.raise_for_status()
    codes = response.json().get("delivery_codes") or []
    for row in codes:
        postal = row.get("postal_code", {})
        if str(postal.get("pin")) == str(pincode) and not postal.get("remarks"):
            return postal
    raise PickupSetupError("Delhivery does not currently service this PIN code.")


def validate_destination(order):
    postal = _pin_details(order.pincode)
    service = "cod" if order.payment_method == "cod" else "pre_paid"
    if str(postal.get(service, "N")).upper() != "Y":
        raise PickupSetupError("Delhivery does not support this payment method at the customer's PIN code.")


def ensure_seller_warehouse(seller):
    """Register each verified seller address once, preserving existing manual mappings."""
    from accounts.models import SellerProfile
    with transaction.atomic():
        seller = SellerProfile.objects.select_for_update().get(pk=seller.pk)
        fingerprint = hashlib.sha256(json.dumps({
            "address": seller.business_address.strip(), "pin": seller.business_pincode,
            "lat": str(seller.business_latitude), "lon": str(seller.business_longitude),
        }, sort_keys=True).encode()).hexdigest()
        registration = seller.courier_warehouses.filter(fingerprint=fingerprint).first()
        if registration:
            if registration.status == "registered":
                return registration.name
            raise PickupSetupError(registration.error or "Pickup address registration needs marketplace review; no duplicate request was sent.")
        if seller.delhivery_pickup_name and not seller.courier_warehouses.exists():
            registration = DelhiveryWarehouseRegistration.objects.create(
                seller=seller, fingerprint=fingerprint, name=seller.delhivery_pickup_name,
                status="registered", response_payload={"source": "existing_admin_mapping"},
            )
            return registration.name
        if not seller.is_approved or seller.is_small_seller:
            raise PickupSetupError("This seller is not approved for courier shipping.")
        if not all((seller.business_address.strip(), seller.business_pincode, seller.business_phone, seller.user.email,
                    seller.business_gps_verified_at)):
            raise PickupSetupError("Complete the seller pickup address, phone, email and verified GPS in Store settings first.")
        # A deterministic name prevents duplicate warehouses after a lost response.
        name = f"ZIYA-{seller.pk}-{fingerprint[:12]}"
        registration = DelhiveryWarehouseRegistration.objects.create(seller=seller, fingerprint=fingerprint, name=name)
    try:
        postal = _pin_details(seller.business_pincode)
        if str(postal.get("pickup", "N")).upper() != "Y":
            raise PickupSetupError("Delhivery pickup is unavailable at this seller's PIN code.")
        city, state = postal.get("city"), postal.get("state_code")
        if not city or not state:
            raise PickupSetupError("Delhivery could not verify the seller's pickup city and state.")
        data = {
            "name": name, "registered_name": name, "phone": seller.business_phone,
            "email": seller.user.email, "address": seller.business_address,
            "pin": seller.business_pincode, "city": city, "country": "India",
            "return_address": seller.business_address, "return_pin": seller.business_pincode,
            "return_city": city, "return_state": state, "return_country": "India",
        }
        response = requests.post("https://track.delhivery.com/api/backend/clientwarehouse/create/", json=data, headers=_headers(), timeout=15)
        registration.response_payload = response.json()
        response.raise_for_status()
        if registration.response_payload.get("success") is not True:
            raise PickupSetupError("Delhivery did not confirm the pickup address registration. Contact marketplace support.")
        registration.status = "registered"
        SellerProfile.objects.filter(pk=seller.pk).update(delhivery_pickup_name=name)
    except Exception as exc:
        registration.status = "review"
        registration.error = str(exc)[:1000]
        registration.save(update_fields=["status", "error", "response_payload", "updated_at"])
        raise PickupSetupError("Pickup address registration needs review. Check the seller details and Delhivery response before retrying.") from exc
    registration.save(update_fields=["status", "response_payload", "updated_at"])
    return name


def parcel_ready(charge):
    order = charge.parcel_order
    if not order or order.status in {"Cancelled", "Returned", "Delivered"}:
        return False
    if order.payment_method != "cod" and order.payment_status != "Paid":
        return False
    items = order.items.filter(product__seller_id=charge.seller_id).exclude(fulfillment_status="cancelled")
    return items.exists() and (order.status == "Packed" or not items.exclude(fulfillment_status="packed").exists())


def pickup_slot():
    local = timezone.localtime()
    slot = time.fromisoformat(getattr(settings, "DELHIVERY_PICKUP_TIME", "14:00:00"))
    day = local.date()
    if local.hour >= int(getattr(settings, "DELHIVERY_PICKUP_CUTOFF_HOUR", 12)) or datetime.combine(day, slot) <= local.replace(tzinfo=None) + timedelta(hours=2):
        day += timedelta(days=1)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day, slot


def reconcile_pickup(request):
    """Only confirmed carrier movement releases the warehouse for a new pickup."""
    if request.status != "scheduled":
        return
    charges = list(request.shipments.exclude(awb_number=""))
    if not charges:
        return
    collected = True
    for charge in charges:
        response = requests.get("https://track.delhivery.com/api/v1/packages/json/", params={"waybill": charge.awb_number}, headers=_headers(), timeout=10)
        response.raise_for_status()
        rows = response.json().get("ShipmentData") or []
        shipment = rows[0].get("Shipment", {}) if len(rows) == 1 else {}
        if str(shipment.get("AWB", "")) != charge.awb_number:
            collected = False
            continue
        status = shipment.get("Status", {}).get("Status", "")
        if status.lower() not in COLLECTED_STATUSES:
            collected = False
        elif not charge.parcel_order.items.filter(product__seller_id=charge.seller_id).exclude(fulfillment_status__in=("packed", "cancelled")).exists():
            charge.parcel_order.items.filter(product__seller_id=charge.seller_id, fulfillment_status="packed").update(
                fulfillment_status="shipped", seller_courier="Delhivery", seller_tracking_number=charge.awb_number,
            )
        if status:
            SellerDeliveryCharge.objects.filter(pk=charge.pk).update(carrier_status=status)
    if collected:
        with transaction.atomic():
            request = DelhiveryPickupRequest.objects.select_for_update().get(pk=request.pk)
            if set(request.shipments.values_list("pk", flat=True)) == {c.pk for c in charges}:
                request.status = "completed"
                request.save(update_fields=["status", "updated_at"])


def schedule_charge_pickup(charge_id, retry=False):
    from .shipping import manifest_delhivery_charge
    charge = SellerDeliveryCharge.objects.select_related("parcel_order", "seller", "pickup_request").get(pk=charge_id)
    if charge.provider != "delhivery" or not parcel_ready(charge):
        return None
    if not charge.awb_number:
        charge = manifest_delhivery_charge(charge.parcel_order, charge)
        if not charge.awb_number:
            return None
    name = charge.pickup_location_name
    if not name:
        # Legacy shipments were manifested against this administrator mapping.
        name = charge.seller.delhivery_pickup_name if charge.seller_id else settings.DELHIVERY_PICKUP_LOCATION
    if not name:
        raise PickupSetupError("This shipment has no confirmed pickup location. Contact marketplace support.")
    active = DelhiveryPickupRequest.objects.filter(pickup_location=name, status="scheduled").first()
    if active:
        reconcile_pickup(active)
    with transaction.atomic():
        charge = SellerDeliveryCharge.objects.select_for_update().get(pk=charge_id)
        if not parcel_ready(charge):
            return None
        existing = DelhiveryPickupRequest.objects.select_for_update().filter(pickup_location=name, status__in=ACTIVE_PICKUPS).first()
        if existing:
            charge.pickup_request = existing
            charge.pickup_error = existing.error
            charge.save(update_fields=["pickup_request", "pickup_error"])
            return existing
        if charge.pickup_request_id and not retry:
            return charge.pickup_request
        if charge.pickup_request_id and charge.pickup_request.status != "failed":
            return charge.pickup_request
        day, slot = pickup_slot()
        try:
            with transaction.atomic():
                pickup = DelhiveryPickupRequest.objects.create(pickup_location=name, pickup_date=day, pickup_time=slot)
        except IntegrityError:
            pickup = DelhiveryPickupRequest.objects.get(pickup_location=name, status__in=ACTIVE_PICKUPS)
            charge.pickup_request = pickup
            charge.save(update_fields=["pickup_request"])
            return pickup
        charge.pickup_request = pickup
        charge.pickup_error = ""
        charge.save(update_fields=["pickup_request", "pickup_error"])
    # The requesting record is committed before the carrier call. Never retry
    # a timeout/unknown response automatically: the carrier may have saved it.
    try:
        response = requests.post("https://track.delhivery.com/fm/request/new/", headers=_headers(), json={
            "pickup_location": name, "pickup_date": str(day), "pickup_time": slot.isoformat(),
            "expected_package_count": pickup.expected_package_count,
        }, timeout=15)
        payload = response.json()
        pickup.response_payload = payload
        if response.status_code in (401, 403):
            pickup.status = "failed"
            pickup.error = "Delhivery access was rejected. Marketplace support must correct the carrier credentials."
        elif "client is on auto pickup" in json.dumps(payload).lower():
            pickup.status = "auto_pickup"
        elif response.ok and payload.get("pickup_id") and payload.get("success") is not False:
            pickup.status = "scheduled"
            pickup.provider_pickup_id = str(payload["pickup_id"])
        else:
            pickup.status = "review"
            pickup.error = "Delhivery did not confirm a pickup ID. Marketplace support must reconcile this response before another request."
    except Exception as exc:
        pickup.status = "review"
        pickup.error = f"Pickup response is uncertain; check Delhivery before retrying. {str(exc)[:500]}"
    pickup.save(update_fields=["status", "provider_pickup_id", "response_payload", "error", "updated_at"])
    SellerDeliveryCharge.objects.filter(pk=charge_id).update(pickup_error=pickup.error)
    return pickup


def queue_order_pickups(order_id, seller_id=None, retry=False):
    """Run after the seller/admin transaction commits, without losing packed state."""
    def run():
        charges = SellerDeliveryCharge.objects.filter(parcel_order_id=order_id, provider="delhivery")
        if seller_id is not None:
            charges = charges.filter(seller_id=seller_id)
        for pk in charges.values_list("pk", flat=True):
            try:
                schedule_charge_pickup(pk, retry=retry)
            except Exception as exc:
                logger.exception("Delhivery pickup failed for package %s", pk)
                SellerDeliveryCharge.objects.filter(pk=pk).update(pickup_error=str(exc)[:1000])
    transaction.on_commit(run)
