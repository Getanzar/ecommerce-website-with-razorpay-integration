from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import AccountDeletionRequest, DeviceSession, PushDevice, Notification


@transaction.atomic
def execute_deletion(pk):
    """Erase customer account data after obligations close; preserve transaction records."""
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    from accounts.models import UserProfile, EmailOTP, PasswordResetOTP
    from addresses.models import Address
    from cart.models import Cart
    from food.models import FoodOrder, FoodCartItem
    from groceries.models import GroceryOrder, GroceryCartItem
    from orders.models import Order
    from products.models import Wishlist

    row = AccountDeletionRequest.objects.select_for_update().get(pk=pk)
    user = User.objects.select_for_update().get(pk=row.user_id)
    if row.status == "Completed":
        return row
    if user.is_staff or user.is_superuser or hasattr(user, "seller_profile") or hasattr(user, "delivery_agent"):
        raise ValidationError("Partner/staff account deletion requires a separate payout, identity and retention review. Disable access while reviewing.")
    if Order.objects.filter(user=user).exclude(status__in=["Delivered", "Cancelled", "Returned"]).exists() or FoodOrder.objects.filter(user=user).exclude(status__in=["delivered", "cancelled"]).exists() or GroceryOrder.objects.filter(user=user).exclude(status__in=["delivered", "cancelled"]).exists():
        raise ValidationError("Open orders must be resolved before account data is erased.")
    from payments.models import RefundTransaction
    if RefundTransaction.objects.filter(payment__user=user, status__in=["requested", "processing"]).exists():
        raise ValidationError("An outstanding refund requires reconciliation before deletion.")
    from .models import CustomerCareRequest
    if CustomerCareRequest.objects.filter(user=user).exclude(status__in=["Closed", "Resolved", "Rejected", "Completed"]).exists():
        raise ValidationError("Close outstanding support and return requests before deletion.")
    profile = UserProfile.objects.filter(user=user).first()
    if profile:
        if profile.profile_picture:
            storage, name = profile.profile_picture.storage, profile.profile_picture.name
            transaction.on_commit(lambda: storage.delete(name))
        profile.phone = ""
        profile.gender = ""
        profile.date_of_birth = None
        profile.profile_picture = ""
        profile.email_verified = False
        profile.phone_verified = False
        profile.save()
    for model in (Address, Cart, FoodCartItem, GroceryCartItem, Wishlist, EmailOTP, PasswordResetOTP, PushDevice, Notification):
        model.objects.filter(user=user).delete()
    DeviceSession.objects.filter(user=user).update(revoked_at=timezone.now(), device_name="Deleted device")
    Token.objects.filter(user=user).delete()
    user.username = f"deleted-account-{user.pk}"
    user.first_name = user.last_name = user.email = ""
    user.is_active = False
    user.set_unusable_password()
    user.save()
    row.status = "Completed"
    row.reason = "Account data erased; transaction/support records retained for operational reconciliation."
    row.save(update_fields=["status", "reason"])
    return row
