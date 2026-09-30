"""Native checkout completion and recovery; provider capture is authoritative."""
import hashlib
import hmac

import razorpay
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle

from payments.models import PaymentTransaction
from payments.services import order_link, _sync_order_payment
from .views import _owned_order, _checkout_response


def payment_payload(order, kind):
    payload = _checkout_response(order, kind)
    if order.payment_method == "online" and order.payment_status != "Paid" and order.status.lower() not in {"cancelled", "returned"}:
        payment = PaymentTransaction.objects.filter(**order_link(order), provider="razorpay").first()
        if payment and payment.status not in {"refunded", "partially_refunded"}:
            payload["razorpay"] = {"key_id": settings.RAZORPAY_KEY_ID, "order_id": payment.provider_order_id,
                                   "amount": int(payment.amount * 100), "currency": "INR", "name": "ZIYAMART"}
    return payload


class PaymentThrottle(UserRateThrottle):
    rate = "20/min"


def provider_call(call, *args):
    try:
        return call(*args, timeout=15)
    except (requests.RequestException, razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError):
        from rest_framework.exceptions import APIException
        error = APIException("Payment confirmation is temporarily unavailable. Check this saved order again shortly.")
        error.status_code = 503
        raise error


class NativePaymentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentThrottle]

    def get(self, request, kind, pk):
        return Response(payment_payload(_owned_order(request.user, kind, pk), kind))

    @transaction.atomic
    def post(self, request, kind, pk):
        order = _owned_order(request.user, kind, pk)
        order = type(order).objects.select_for_update().get(pk=order.pk)
        payment = PaymentTransaction.objects.select_for_update().filter(**order_link(order), provider="razorpay").first()
        if not payment:
            raise ValidationError("No online payment exists for this order.")
        action = request.data.get("action", "verify")
        if action in {"cancelled", "failed"}:
            # A client dismissal cannot invalidate a payment captured concurrently.
            return Response(payment_payload(order, kind))
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        if action == "verify":
            payment_id = str(request.data.get("razorpay_payment_id", ""))
            provider_id = str(request.data.get("razorpay_order_id", ""))
            signature = str(request.data.get("razorpay_signature", ""))
            expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), f"{payment.provider_order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
            if provider_id != payment.provider_order_id or not payment_id or not hmac.compare_digest(expected, signature):
                raise ValidationError("Invalid payment signature.")
            entities = [provider_call(client.payment.fetch, payment_id)]
        elif action == "recover":
            entities = provider_call(client.order.payments, payment.provider_order_id).get("items", [])
        else:
            raise ValidationError("Unknown payment action.")
        for entity in entities:
            if entity.get("status") != "captured":
                continue
            if entity.get("order_id") != payment.provider_order_id or entity.get("amount") != int(payment.amount * 100) or entity.get("currency") != "INR":
                raise ValidationError("Provider payment does not match this order.")
            if payment.status in {"captured", "partially_refunded", "refunded"}:
                break
            if order.status.lower() in {"cancelled", "returned"}:
                raise ValidationError("Payment received for a closed order. Contact support for reconciliation.")
            payment.provider_payment_id = entity["id"]
            payment.status = "captured"
            payment.captured_at = timezone.now()
            payment.failure_reason = ""
            payment.save()
            _sync_order_payment(payment, True)
            break
        order.refresh_from_db()
        return Response(payment_payload(order, kind))
