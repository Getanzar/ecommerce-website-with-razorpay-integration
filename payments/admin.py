from django.contrib import admin

from .models import (
    ChargeBreakdown, CODRemittance, PaymentTransaction, PaymentWebhookEvent,
    RefundTransaction, SellerDeliveryCharge,
    DelhiveryWarehouseRegistration, DelhiveryPickupRequest,
)


for model in (
    ChargeBreakdown, PaymentTransaction, PaymentWebhookEvent,
    RefundTransaction, SellerDeliveryCharge, CODRemittance, DelhiveryWarehouseRegistration, DelhiveryPickupRequest,
):
    admin.site.register(model)
