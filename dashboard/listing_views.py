from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from rest_framework.response import Response

from accounts.models import SellerProfile
from mobile_api.partners import PartnerView, seller_for
from .listing_assistant import ListingAssistantError, generate_draft


def draft_response(seller, data, files):
    try:
        result = generate_draft(seller, data.get("kind", ""), data.get("notes", ""), files.getlist("photos"))
        return result, 200
    except ListingAssistantError as exc:
        return {"error": str(exc)}, exc.status


@login_required
@require_POST
def seller_listing_draft(request):
    seller = get_object_or_404(SellerProfile, user=request.user)
    result, status = draft_response(seller, request.POST, request.FILES)
    return JsonResponse(result, status=status)


class SellerListingDraftView(PartnerView):
    def post(self, request):
        result, status = draft_response(seller_for(request.user), request.data, request.FILES)
        return Response(result, status=status)
