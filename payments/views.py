from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_razorpay_event


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    if not event_id:
        return HttpResponseBadRequest("Missing webhook event id")
    try:
        handle_razorpay_event(
            request.body,
            request.headers.get("X-Razorpay-Signature", ""),
            event_id,
        )
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Invalid webhook")
    return HttpResponse(status=200)
