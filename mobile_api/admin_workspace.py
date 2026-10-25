"""Read-only native operations overview; mutations retain the web audit workflows."""
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.models import SellerProfile
from dashboard.security import can_access_operations
from delivery.models import LocalDelivery
from orders.models import Order, SupportTicket
from products.models import Product
from .partners import PartnerView


class AdminWorkspaceView(PartnerView):
    def get(self, request):
        if not can_access_operations(request.user):
            raise PermissionDenied("Operations access is required.")
        return Response({
            "metrics": {
                "pending_sellers": SellerProfile.objects.filter(status="pending").count(),
                "pending_products": Product.objects.filter(moderation_status="pending").count(),
                "orders": Order.objects.count(),
                "active_deliveries": LocalDelivery.objects.exclude(status__in=["delivered", "cancelled"]).count(),
                "support_tickets": SupportTicket.objects.count(),
            },
            "pending_products": list(Product.objects.filter(moderation_status="pending").order_by("-pk").values("id", "name", "seller__store_name")[:20]),
            "pending_sellers": list(SellerProfile.objects.filter(status="pending").order_by("-pk").values("id", "store_name", "business_segment")[:20]),
        })
