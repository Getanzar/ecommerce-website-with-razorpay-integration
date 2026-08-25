import requests
from django.conf import settings


class AgentPayoutError(RuntimeError):
    pass


def provision_agent_payout_account(agent, account_number):
    auth = (settings.RAZORPAYX_KEY_ID, settings.RAZORPAYX_KEY_SECRET)
    if not all(auth):
        raise AgentPayoutError("RazorpayX credentials are not configured.")
    try:
        if not agent.razorpay_contact_id:
            response = requests.post(
                "https://api.razorpay.com/v1/contacts",
                auth=auth,
                json={
                    "name": agent.bank_account_holder or agent.full_name,
                    "email": agent.user.email,
                    "contact": agent.phone,
                    "type": "employee",
                    "reference_id": f"delivery-agent-{agent.pk}",
                    "notes": {"pincode": agent.pincode},
                },
                timeout=30,
            )
            response.raise_for_status()
            agent.razorpay_contact_id = response.json()["id"]
        response = requests.post(
            "https://api.razorpay.com/v1/fund_accounts",
            auth=auth,
            json={
                "contact_id": agent.razorpay_contact_id,
                "account_type": "bank_account",
                "bank_account": {
                    "name": agent.bank_account_holder,
                    "ifsc": agent.bank_ifsc_code,
                    "account_number": account_number,
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        agent.razorpay_fund_account_id = response.json()["id"]
        agent.payouts_enabled = False
        agent.save(update_fields=["razorpay_contact_id", "razorpay_fund_account_id", "payouts_enabled", "updated_at"])
        return agent.razorpay_fund_account_id
    except (requests.RequestException, KeyError) as exc:
        raise AgentPayoutError("RazorpayX could not create the delivery-agent payout account.") from exc


def submit_agent_payout(earning):
    agent = earning.agent
    if not agent.payouts_enabled or not agent.razorpay_fund_account_id:
        raise AgentPayoutError("The delivery-agent payout account is not verified and enabled.")
    if not all((settings.RAZORPAYX_KEY_ID, settings.RAZORPAYX_KEY_SECRET, settings.RAZORPAYX_ACCOUNT_NUMBER)):
        raise AgentPayoutError("RazorpayX payout credentials are not configured.")
    try:
        response = requests.post(
            "https://api.razorpay.com/v1/payouts",
            auth=(settings.RAZORPAYX_KEY_ID, settings.RAZORPAYX_KEY_SECRET),
            headers={"X-Payout-Idempotency": earning.payout_idempotency_key},
            json={
                "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
                "fund_account_id": agent.razorpay_fund_account_id,
                "amount": int(earning.net_amount * 100),
                "currency": "INR",
                "mode": settings.SELLER_PAYOUT_MODE,
                "purpose": "payout",
                "queue_if_low_balance": True,
                "reference_id": f"agent-earning-{earning.pk}",
                "narration": "ZIYAMART delivery payout",
                "notes": {"earning_id": str(earning.pk), "delivery_id": str(earning.delivery_id)},
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise AgentPayoutError("Delivery-agent payout submission failed.") from exc
