from django.contrib import admin

from .models import (
    ChargeBreakdown, CODRemittance, PaymentTransaction, PaymentWebhookEvent,
    RefundTransaction, SellerDeliveryCharge,
)


for model in (
    ChargeBreakdown, PaymentTransaction, PaymentWebhookEvent,
    RefundTransaction, SellerDeliveryCharge, CODRemittance,
):
    admin.site.register(model)
