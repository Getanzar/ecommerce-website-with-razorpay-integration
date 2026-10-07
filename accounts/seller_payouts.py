from decimal import Decimal

import requests
from django.conf import settings


class SellerPayoutError(RuntimeError):
    pass


def submit_seller_payout(settlement):
    """
    Submit a marketplace seller settlement to RazorpayX.

    Supports general marketplace, food, and grocery settlements because
    each settlement exposes seller, payout_amount, and payout_reference_key.
    """
    seller = settlement.seller

    if settlement.status == "paid":
        raise SellerPayoutError("This seller settlement has already been paid.")

    if settlement.status == "processing" and settlement.provider_payout_id:
        raise SellerPayoutError("This seller settlement is already processing.")

    if settlement.status not in {"scheduled", "failed"}:
        raise SellerPayoutError(
            f"Settlement status '{settlement.status}' is not eligible for payout."
        )

    if not seller.payouts_enabled:
        raise SellerPayoutError(
            "The seller payout account is not verified and enabled."
        )

    if not seller.razorpay_fund_account_id:
        raise SellerPayoutError(
            "The seller does not have a RazorpayX fund account."
        )

    key_id = getattr(settings, "RAZORPAYX_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAYX_KEY_SECRET", "")
    account_number = getattr(settings, "RAZORPAYX_ACCOUNT_NUMBER", "")

    if not all((key_id, key_secret, account_number)):
        raise SellerPayoutError(
            "RazorpayX payout credentials are not configured."
        )

    amount = Decimal(settlement.payout_amount)

    if amount <= Decimal("0.00"):
        raise SellerPayoutError(
            "Settlement payout amount must be greater than zero."
        )

    amount_paise = int(amount * 100)

    try:
        response = requests.post(
            "https://api.razorpay.com/v1/payouts",
            auth=(key_id, key_secret),
            headers={
                "X-Payout-Idempotency": settlement.payout_reference_key,
            },
            json={
                "account_number": account_number,
                "fund_account_id": seller.razorpay_fund_account_id,
                "amount": amount_paise,
                "currency": "INR",
                "mode": getattr(settings, "SELLER_PAYOUT_MODE", "IMPS"),
                "purpose": "payout",
                "queue_if_low_balance": True,
                "reference_id": settlement.payout_reference_key,
                "narration": "ZIYAMART seller payout",
                "notes": {
                    "settlement_id": str(settlement.pk),
                    "seller_id": str(seller.pk),
                    "reference": settlement.payout_reference_key,
                },
            },
            timeout=30,
        )

        response.raise_for_status()
        payload = response.json()

        payout_id = payload.get("id")
        if not payout_id:
            raise SellerPayoutError(
                "RazorpayX returned a payout response without a payout id."
            )

        return payload

    except requests.RequestException as exc:
        detail = ""

        if getattr(exc, "response", None) is not None:
            try:
                detail = (
                    exc.response.json()
                    .get("error", {})
                    .get("description", "")
                )
            except (ValueError, AttributeError):
                pass

        raise SellerPayoutError(
            detail or "Seller payout submission to RazorpayX failed."
        ) from exc