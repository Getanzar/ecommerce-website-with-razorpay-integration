import requests
from django.conf import settings


class PayoutOnboardingError(Exception):
    pass


def provision_seller_payout_account(seller, bank_account_number):
    """Send bank data directly to RazorpayX; persist only provider tokens."""
    key_id = getattr(settings, "RAZORPAYX_KEY_ID", "") or getattr(settings, "RAZORPAY_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAYX_KEY_SECRET", "") or getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise PayoutOnboardingError("RazorpayX API credentials are not configured.")

    auth = (key_id, key_secret)
    try:
        if not seller.razorpay_contact_id:
            contact_response = requests.post(
                "https://api.razorpay.com/v1/contacts",
                auth=auth,
                json={
                    "name": seller.bank_account_holder or seller.legal_business_name,
                    "email": seller.user.email,
                    "contact": seller.business_phone,
                    "type": "vendor",
                    "reference_id": f"seller-{seller.pk}",
                    "notes": {"store_name": seller.store_name},
                }, timeout=30,
            )
            contact_response.raise_for_status()
            seller.razorpay_contact_id = contact_response.json()["id"]

        fund_response = requests.post(
            "https://api.razorpay.com/v1/fund_accounts",
            auth=auth,
            json={
                "contact_id": seller.razorpay_contact_id,
                "account_type": "bank_account",
                "bank_account": {
                    "name": seller.bank_account_holder,
                    "ifsc": seller.bank_ifsc_code,
                    "account_number": bank_account_number,
                },
            }, timeout=30,
        )
        fund_response.raise_for_status()
        seller.razorpay_fund_account_id = fund_response.json()["id"]
        seller.payouts_enabled = False
        seller.save(update_fields=[
            "razorpay_contact_id", "razorpay_fund_account_id",
            "payouts_enabled", "updated_at",
        ])
        return seller.razorpay_fund_account_id
    except (requests.RequestException, KeyError) as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("error", {}).get("description", "")
            except ValueError:
                pass
        raise PayoutOnboardingError(detail or "RazorpayX could not create the payout account.") from exc
