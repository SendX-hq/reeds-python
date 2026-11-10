import os

from flask import Flask, request

from reeds import WebhookSignatureError, webhooks

app = Flask(__name__)


@app.post("/webhooks/reeds")
def reeds_webhook() -> tuple[str, int]:
    try:
        event = webhooks.construct_event(request.get_data(), request.headers.get("Reeds-Signature"), os.environ["REEDS_WEBHOOK_SECRET"])
    except WebhookSignatureError as error:
        return error.message, 400
    print(event.id, event.type)  # handle the event here
    return "", 200
