import math
import logging
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings


CENT = Decimal("0.01")
HUNDRED = Decimal("100")
LOCAL_CUSTOMER_DELIVERY_FEE = Decimal("20.00")
LOCAL_FREE_DELIVERY_MINIMUM = Decimal("200.00")
logger = logging.getLogger(__name__)


class DeliveryQuoteError(RuntimeError):
    pass


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def percentage(value, rate):
    return money(Decimal(value) * Decimal(str(rate)) / HUNDRED)


def _configured_decimal(name, default):
    return Decimal(str(getattr(settings, name, default)))


def _haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return _configured_decimal("LOCAL_DELIVERY_INCLUDED_KM", "2.00")
    values = [math.radians(float(value)) for value in (lat1, lon1, lat2, lon2)]
    a_lat, a_lon, b_lat, b_lon = values
    delta_lat, delta_lon = b_lat - a_lat, b_lon - a_lon
    arc = math.sin(delta_lat / 2) ** 2 + math.cos(a_lat) * math.cos(b_lat) * math.sin(delta_lon / 2) ** 2
    # A modest road factor avoids presenting straight-line distance as a route.
    return money(6371 * 2 * math.asin(math.sqrt(arc)) * 1.25)


def quote_local_delivery(origin_lat, origin_lon, destination_lat, destination_lon):
    distance = _haversine_km(origin_lat, origin_lon, destination_lat, destination_lon)
    base = _configured_decimal("LOCAL_DELIVERY_BASE_FEE", "30.00")
    included = _configured_decimal("LOCAL_DELIVERY_INCLUDED_KM", "2.00")
    per_km = _configured_decimal("LOCAL_DELIVERY_PER_KM", "8.00")
    extra_km = max(0, math.ceil(float(distance - included)))
    total = money(base + per_km * extra_km)
    return {
        "provider": "local",
        "distance_km": distance,
        "carrier_amount": total,
        "handling_fee": Decimal("0.00"),
        "tax_amount": Decimal("0.00"),
        "quoted_total": total,
        "quote_payload": {"method": "gps_distance", "extra_started_km": extra_km},
    }


def chargeable_weight_grams(items):
    actual = 0
    volumetric = Decimal("0")
    for row in items:
        product = row["product"]
        quantity = int(row["quantity"])
        actual += product.package_weight_grams * quantity
        volume_kg = (
            Decimal(product.package_length_cm)
            * Decimal(product.package_width_cm)
            * Decimal(product.package_height_cm)
            / Decimal("5000")
        )
        volumetric += volume_kg * 1000 * quantity
    return max(actual, int(volumetric.to_integral_value(rounding=ROUND_HALF_UP)), 1)


def _extract_delhivery_amount(payload, field=None):
    if isinstance(payload, dict) and (payload.get("error") or payload.get("success") is False):
        return None
    preferred = (field,) if field else ("total_amount", "total", "amount", "shipping_charge", "gross_amount")
    if isinstance(payload, dict):
        for key in preferred:
            value = payload.get(key)
            if isinstance(value, (int, float, str)):
                try:
                    amount = money(value)
                    if amount.is_finite() and amount > 0:
                        return amount
                except Exception:
                    pass
        for value in payload.values():
            found = _extract_delhivery_amount(value, field)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _extract_delhivery_amount(value, field)
            if found is not None:
                return found
    return None


def quote_delhivery(origin_pincode, destination_pincode, weight_grams, payment_method, *, require_live=None):
    payload = {}
    carrier_amount = None
    require_live = settings.DELHIVERY_REQUIRE_LIVE_QUOTE if require_live is None else require_live
    api_key = getattr(settings, "DELHIVERY_API_KEY", "")
    if api_key:
        try:
            # Rate lookup is read-only: retry a transient network/server failure
            # once, but never retry rejected credentials or invalid pincodes.
            for attempt in range(2):
                try:
                    response = requests.get(
                        settings.DELHIVERY_RATE_URL,
                        params={
                            "md": "S",
                            "ss": "Delivered",
                            "d_pin": destination_pincode,
                            "o_pin": origin_pincode,
                            "cgm": weight_grams,
                            "pt": "COD" if payment_method == "cod" else "Pre-paid",
                        },
                        headers={"Authorization": f"Token {api_key}"},
                        timeout=max(0.5, float(settings.DELHIVERY_RATE_TIMEOUT) / 2),
                    )
                    response.raise_for_status()
                    break
                except requests.RequestException as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if attempt or (status is not None and status != 429 and status < 500):
                        raise
            payload = response.json()
            carrier_amount = _extract_delhivery_amount(payload, "total_amount")
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logger.warning(
                "Delhivery rate lookup failed: origin=%s destination=%s weight=%s payment=%s status=%s error_type=%s",
                origin_pincode, destination_pincode, weight_grams, payment_method, status, type(exc).__name__,
            )
            if require_live:
                if status in (401, 403):
                    raise DeliveryQuoteError("Courier rate access is unavailable. Please contact support to complete your order.") from exc
                raise DeliveryQuoteError("Courier rates are temporarily unavailable. Please try checkout again in a moment.") from exc
            payload = {"fallback_reason": str(exc)[:250]}
    if carrier_amount is None:
        if require_live:
            raise DeliveryQuoteError("Delhivery returned an invalid shipping quote.")
        slabs = max(1, math.ceil(weight_grams / 500))
        carrier_amount = money(
            _configured_decimal("DELHIVERY_FALLBACK_BASE", "60.00")
            + _configured_decimal("DELHIVERY_FALLBACK_PER_500G", "25.00") * (slabs - 1)
        )
        payload = {"carrier_response": payload, "fallback": True}
        payload["weight_slabs"] = slabs
    if carrier_amount is not None and not (isinstance(payload, dict) and payload.get("fallback")):
        # Delhivery total_amount already includes tax. Pass that total through
        # without a handling markup or charging GST a second time.
        total = carrier_amount
        base = _extract_delhivery_amount(payload, "gross_amount")
        if base is None:
            base = money(total / (1 + _configured_decimal("DELHIVERY_GST_PERCENT", "18.00") / HUNDRED))
        if base > total:
            raise DeliveryQuoteError("Delhivery returned an invalid shipping quote.")
        return {
            "provider": "delhivery", "distance_km": Decimal("0.00"),
            "carrier_amount": base, "handling_fee": Decimal("0.00"),
            "tax_amount": money(total - base), "quoted_total": total,
            "quote_payload": {"carrier_response": payload, "tax_included": True},
        }
    handling = money(_configured_decimal("DELHIVERY_HANDLING_FEE", "5.00"))
    taxable = carrier_amount + handling
    tax = percentage(taxable, _configured_decimal("DELHIVERY_GST_PERCENT", "18.00"))
    return {
        "provider": "delhivery",
        "distance_km": Decimal("0.00"),
        "carrier_amount": carrier_amount,
        "handling_fee": handling,
        "tax_amount": tax,
        "quoted_total": money(taxable + tax),
        "quote_payload": payload,
    }


def line_charges(seller_unit_price, customer_unit_price, quantity, merchandise_gst_rate):
    base = money(Decimal(seller_unit_price) * quantity)
    platform = money((Decimal(customer_unit_price) - Decimal(seller_unit_price)) * quantity)
    merchandise_gst = percentage(base, merchandise_gst_rate)
    platform_gst = percentage(platform, _configured_decimal("PLATFORM_FEE_GST_PERCENT", "18.00"))
    return {
        "merchant_subtotal": base,
        "platform_fee": platform,
        "merchandise_gst": merchandise_gst,
        "platform_fee_gst": platform_gst,
    }


def _sum_charges(rows):
    keys = ("merchant_subtotal", "platform_fee", "merchandise_gst", "platform_fee_gst")
    return {key: money(sum((row[key] for row in rows), Decimal("0"))) for key in keys}


def build_food_pricing(rows, restaurant):
    lines = [
        line_charges(
            row["option"].price,
            row["option"].customer_price,
            row["quantity"],
            _configured_decimal("RESTAURANT_GST_PERCENT", "5.00"),
        )
        for row in rows
    ]
    totals = _sum_charges(lines)
    delivery = LOCAL_CUSTOMER_DELIVERY_FEE
    item_total = money(sum(totals.values()))
    customer_delivery = Decimal("0.00") if item_total >= LOCAL_FREE_DELIVERY_MINIMUM else delivery
    totals.update({
        "delivery_fee": delivery,
        "delivery_gst": Decimal("0.00"),
        "seller_sponsored_delivery": delivery - customer_delivery,
        "customer_delivery_charge": customer_delivery,
        "delivery_mode": "local",
    })
    totals["grand_total"] = money(
        totals["merchant_subtotal"] + totals["platform_fee"]
        + totals["merchandise_gst"] + totals["platform_fee_gst"] + customer_delivery
    )
    return totals


def build_grocery_pricing(rows, store):
    lines = [
        line_charges(
            row.get("option", row["product"]).price,
            row.get("option", row["product"]).customer_price,
            row["quantity"],
            row["product"].gst_rate,
        )
        for row in rows
    ]
    totals = _sum_charges(lines)
    delivery = LOCAL_CUSTOMER_DELIVERY_FEE
    item_total = money(sum(totals.values()))
    customer_delivery = Decimal("0.00") if item_total >= LOCAL_FREE_DELIVERY_MINIMUM else delivery
    totals.update({
        "delivery_fee": delivery,
        "delivery_gst": Decimal("0.00"),
        "seller_sponsored_delivery": delivery - customer_delivery,
        "customer_delivery_charge": customer_delivery,
        "delivery_mode": "local",
    })
    totals["grand_total"] = money(
        totals["merchant_subtotal"] + totals["platform_fee"]
        + totals["merchandise_gst"] + totals["platform_fee_gst"] + customer_delivery
    )
    return totals


def build_parcel_pricing(items, destination, payment_method):
    from delivery.coverage import has_local_coverage
    if not items:
        raise DeliveryQuoteError("Your cart no longer contains an available product.")
    line_rows = []
    grouped = defaultdict(list)
    for row in items:
        variant = row["variant"]
        line_rows.append(line_charges(
            variant.seller_price, variant.final_price, row["quantity"], row["product"].effective_gst_rate,
        ))
        grouped[row["product"].seller].append(row)
    totals = _sum_charges(line_rows)
    seller_quotes = []
    modes = set()
    for seller, seller_items in grouped.items():
        origin_pincode = (
            seller.business_pincode if seller and seller.business_pincode
            else settings.DELHIVERY_ORIGIN_PINCODE
        )
        weight = chargeable_weight_grams(seller_items)
        if seller and seller.is_small_seller:
            if not seller.is_approved:
                raise DeliveryQuoteError("This small seller is awaiting verification. Remove their items to continue.")
            if origin_pincode != destination["pincode"]:
                raise DeliveryQuoteError(f"{seller.store_name} delivers only within pincode {origin_pincode}. Remove their items or choose a local address.")
            if not has_local_coverage(origin_pincode):
                raise DeliveryQuoteError("Local delivery is currently unavailable for this small seller. Please try again later.")
        if seller and origin_pincode == destination["pincode"] and has_local_coverage(origin_pincode):
            quote = quote_local_delivery(
                seller.business_latitude, seller.business_longitude,
                destination.get("latitude"), destination.get("longitude"),
            )
        else:
            quote = quote_delhivery(
                origin_pincode, destination["pincode"], weight, payment_method,
                require_live=getattr(settings, "PARCEL_CUSTOMER_DELIVERY_LIVE_QUOTES", True),
            )
        modes.add(quote["provider"])
        quote["quote_payload"] = {**quote.get("quote_payload", {}), "delivery_payer": "customer"}
        quote.update({
            "seller": seller,
            "origin_pincode": origin_pincode,
            "destination_pincode": destination["pincode"],
            "chargeable_weight_grams": weight,
            "customer_collection_amount": money(sum((
                sum(line_charges(
                    row["variant"].seller_price,
                    row["variant"].final_price,
                    row["quantity"],
                    row["product"].effective_gst_rate,
                ).values())
                for row in seller_items
            ), Decimal("0"))) + quote["quoted_total"],
        })
        seller_quotes.append(quote)
    delivery_total = money(sum((row["quoted_total"] for row in seller_quotes), Decimal("0")))
    delivery_tax = money(sum((row["tax_amount"] for row in seller_quotes), Decimal("0")))
    totals.update({
        "delivery_fee": money(delivery_total - delivery_tax),
        "delivery_gst": delivery_tax,
        "seller_sponsored_delivery": Decimal("0.00"),
        "customer_delivery_charge": delivery_total,
        "delivery_mode": next(iter(modes)) if len(modes) == 1 else "mixed",
    })
    totals["grand_total"] = money(
        totals["merchant_subtotal"] + totals["platform_fee"]
        + totals["merchandise_gst"] + totals["platform_fee_gst"] + delivery_total
    )
    return totals, seller_quotes
