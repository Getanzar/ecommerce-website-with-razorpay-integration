"""Persist events in the transaction; network delivery is handled by a worker."""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from orders.models import Order
from food.models import FoodOrder
from groceries.models import GroceryOrder
from delivery.models import LocalDelivery
from .models import Notification
from payments.models import RefundTransaction

MODELS = (Order, FoodOrder, GroceryOrder, LocalDelivery)


@receiver(post_save, sender=RefundTransaction)
def refund_updated(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from .models import SellerCase
    case = SellerCase.objects.filter(refund=instance).first()
    if not case:
        return
    target = "resolved" if instance.status == "processed" else "reviewing"
    resolution = f"Refund {instance.status}. Reference: {instance.provider_refund_id or 'awaiting confirmation'}."
    if case.status != target or case.resolution != resolution:
        case.status, case.resolution = target, resolution
        case.save(update_fields=["status", "resolution", "updated_at"])
        Notification.objects.create(user=case.seller.user, title="Refund update", body=resolution, data={"target": "seller", "kind": case.order_kind, "order_id": case.order_id}, category="payment_updates")
        Notification.objects.create(user=instance.payment.user, title="Refund update", body=resolution, data={"kind": case.order_kind, "order_id": case.order_id}, category="payment_updates")


@receiver(pre_save)
def remember_status(sender, instance, raw=False, **kwargs):
    if raw or sender not in MODELS:
        return
    fields = ["status", "agent_id"] if sender is LocalDelivery else ["status", "payment_status"]
    instance._mobile_previous = sender.objects.filter(pk=instance.pk).values(*fields).first() if instance.pk else None


@receiver(post_save)
def record_status(sender, instance, created, raw=False, **kwargs):
    if raw or sender not in MODELS:
        return
    old = getattr(instance, "_mobile_previous", None) or {}
    if sender is LocalDelivery:
        if old.get("status") == instance.status and old.get("agent_id") == instance.agent_id:
            return
        order = instance.source_order
        kind = "shop" if instance.parcel_order_id else "food" if instance.food_order_id else "grocery"
        data = {"kind": kind, "order_id": order.pk, "delivery_id": instance.pk}
        if instance.agent_id:
            Notification.objects.create(user_id=instance.agent.user_id, title="Delivery job update", body=f"Delivery #{instance.pk}: {instance.status}", data={**data, "target": "rider"})
        elif instance.status == "available":
            from delivery.models import DeliveryAgentProfile
            riders = DeliveryAgentProfile.objects.filter(status="approved", is_online=True, pincode=instance.pincode)
            Notification.objects.bulk_create([Notification(user_id=rider.user_id, title="Delivery available", body=f"A delivery is available in {instance.pincode}.", data={**data, "target": "rider"}) for rider in riders])
        if old.get("agent_id") and old["agent_id"] != instance.agent_id:
            from delivery.models import DeliveryAgentProfile
            previous = DeliveryAgentProfile.objects.get(pk=old["agent_id"])
            Notification.objects.create(user_id=previous.user_id, title="Delivery reassigned", body=f"Delivery #{instance.pk} was reassigned by dispatch.", data={**data, "target": "rider"})
        Notification.objects.create(user=order.user, title="Delivery update", body=f"Your delivery is {instance.status.replace('_', ' ')}.", data=data)
        return
    kind = {Order: "shop", FoodOrder: "food", GroceryOrder: "grocery"}[sender]
    data = {"kind": kind, "order_id": instance.pk}
    if created or old.get("status") != instance.status:
        Notification.objects.create(user=instance.user, title="Order update", body=f"Order #{instance.pk}: {instance.status}", data=data)
    if not created and old.get("payment_status") != instance.payment_status:
        Notification.objects.create(user=instance.user, title="Payment update", body=f"Order #{instance.pk} payment: {instance.payment_status}", data=data, category="payment_updates")
