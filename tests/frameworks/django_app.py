import os

from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from reeds import WebhookSignatureError, webhooks


@csrf_exempt  # Reeds signs its requests; there's no CSRF token to send
@require_POST
def reeds_webhook(request: HttpRequest) -> HttpResponse:
    try:
        event = webhooks.construct_event(request.body, request.headers.get("Reeds-Signature"), os.environ["REEDS_WEBHOOK_SECRET"])
    except WebhookSignatureError as error:
        return HttpResponse(error.message, status=400)
    print(event.id, event.type)  # handle the event here
    return HttpResponse(status=200)


urlpatterns = [path("webhooks/reeds", reeds_webhook)]
