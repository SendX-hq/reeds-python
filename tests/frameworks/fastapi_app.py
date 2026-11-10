import os

from fastapi import FastAPI, Request, Response

from reeds import WebhookSignatureError, webhooks

app = FastAPI()


@app.post("/webhooks/reeds")
async def reeds_webhook(request: Request) -> Response:
    try:
        event = webhooks.construct_event(await request.body(), request.headers.get("reeds-signature"), os.environ["REEDS_WEBHOOK_SECRET"])
    except WebhookSignatureError as error:
        return Response(error.message, status_code=400)
    print(event.id, event.type)  # handle the event here
    return Response(status_code=200)
