<p align="center"><img src="https://raw.githubusercontent.com/SendX-hq/reeds-python/main/assets/reeds-logo.png" alt="Reeds" width="240"></p>

<h1 align="center">Reeds Python library</h1>

<p align="center">
  The official Python library for the Reeds APIs: one client for every Reeds service.
</p>

<p align="center">
  <a href="https://pypi.org/project/reeds-sdk/"><img src="https://img.shields.io/pypi/v/reeds-sdk?color=0066F5&label=pypi" alt="PyPI version"></a>
  <a href="https://github.com/SendX-hq/reeds-python/actions/workflows/ci.yml"><img src="https://github.com/SendX-hq/reeds-python/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/pypi/pyversions/reeds-sdk?color=0066F5" alt="Python versions">
  <img src="https://img.shields.io/badge/types-mypy%20%7C%20pyright-0066F5" alt="Typed">
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/reeds-sdk?color=0066F5" alt="MIT license"></a>
</p>

<p align="center">
  <a href="https://developer.getreeds.co">Developer docs</a> ·
  <a href="https://developer.getreeds.co/api">API reference</a> ·
  <a href="https://developer.getreeds.co/changelog">API changelog</a> ·
  <a href="CHANGELOG.md">Library changelog</a>
</p>

---

```python
from reeds import Reeds
from reeds.shipping import Quote

reeds = Reeds()  # reads REEDS_CLIENT_ID and REEDS_CLIENT_SECRET

quote = reeds.shipping.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "Sneakers", "quantity": 1, "weight_kg": 1.5})
if isinstance(quote, Quote):
    delivery = reeds.shipping.deliveries.create(quote_id=quote.id, reference="ORDER-10045")
    print(delivery.tracking_code)  # HQ3W5F2
```

## Contents

- [Services](#services)
- [Why use the library](#why-use-the-library)
- [Install](#install)
- [Credentials and modes](#credentials-and-modes)
- [Shipping](#shipping): [quickstart](#quickstart), [coverage and quotes](#coverage-and-quotes), [address search](#address-search), [deliveries](#deliveries), [statuses](#delivery-statuses), [labels](#labels), [wallet and invoices](#wallet-and-invoices), [sandbox](#test-mode-and-the-sandbox)
- [Async](#async)
- [Webhooks](#webhooks): [FastAPI](#fastapi), [Flask](#flask), [Django](#django)
- [Lists and pagination](#lists-and-pagination)
- [Errors](#errors)
- [Retries, idempotency and timeouts](#retries-idempotency-and-timeouts)
- [Types](#types)
- [Configuration](#configuration)
- [Versioning](#versioning) · [Support](#support) · [License](#license)

## Services

Reeds offers its services as separate APIs. The library gives each one a property on the same client, so one install and one set of credentials cover them all:

| Service | On the client | Status |
|---|---|---|
| **Shipping**: address search, quotes, deliveries, labels, the wallet, invoices, the sandbox | `reeds.shipping` | **Available** |

Webhooks are shared: one endpoint receives every service's events, all verified by `reeds.webhooks`. A new service arrives in a minor version of this library, so upgrading never breaks the services you already use.

## Why use the library

| | |
|---|---|
| **Authentication handled** | It exchanges your client id and secret for an access token, caches it, and refreshes it before it expires. |
| **Safe retries** | Every `POST` carries an `Idempotency-Key`, and a retry reuses it, so a retry never books or charges twice. |
| **Resilient** | It retries rate limits, overload and dropped connections, honouring `Retry-After`. |
| **Typed** | Responses are Pydantic models and parameters are TypedDicts, generated from the API's OpenAPI spec. Your editor completes them; mypy and pyright check them. |
| **Sync and async** | `Reeds` for regular code, `AsyncReeds` for asyncio (FastAPI, aiohttp, Django async views). Same methods. |
| **Pagination** | A `for` loop (or `async for`) walks every page of a list. |
| **Clear errors** | One exception class per kind of failure, with the API's `code`, the invalid `fields`, a `doc_url` and the `request_id`. |
| **Webhooks verified** | `construct_event` checks the signature and returns a typed event. |

## Install

```sh
pip install reeds-sdk
```

Or `uv add reeds-sdk`, or `poetry add reeds-sdk`. Import it as `reeds`. It needs Python 3.11 or later, and installs [HTTPX2](https://github.com/pydantic/httpx2) and [Pydantic](https://docs.pydantic.dev) 2.

## Credentials and modes

Get your client id and secret from **Dashboard → Developers**. Each mode has its own pair:

| Mode | Client id | Client secret | What happens |
|---|---|---|---|
| Test | `rci_test_...` | `rcs_test_...` | Nothing real moves and no real money is spent. Use it to build and test. |
| Live | `rci_live_...` | `rcs_live_...` | Real pickups, real charges. Available once Reeds approves your business. |

```python
import os

from reeds import Reeds

reeds = Reeds(client_id=os.environ["REEDS_CLIENT_ID"], client_secret=os.environ["REEDS_CLIENT_SECRET"])

reeds.mode  # "test" or "live", from the client id
reeds.scopes()  # the services your credentials can use, for example ["shipping"]
```

`client_id` and `client_secret` default to the `REEDS_CLIENT_ID` and `REEDS_CLIENT_SECRET` environment variables. Keep the secret on your server: never put it in a browser or a mobile app.

## Shipping

The [Shipping API](https://developer.getreeds.co/docs/shipping/overview) books pickups and deliveries: within a state, and between states along the routes Reeds runs.

### Quickstart

```python
from reeds import Reeds
from reeds.shipping import QuoteUnavailable

reeds = Reeds()

# 1. Price it.
quote = reeds.shipping.quotes.create(
    pickup={"name": "Tola Fabrics", "phone": "08051234567", "address": "23 Allen Avenue", "area": "Ikeja", "lga": "Ikeja", "state": "Lagos"},
    dropoff={"name": "Chinedu Eze", "phone": "08098765432", "address": "14 Admiralty Way", "area": "Lekki Phase 1", "lga": "Eti-Osa", "state": "Lagos"},
    package={"description": "2 pairs of sneakers", "quantity": 1, "weight_kg": 1.5},
)

if isinstance(quote, QuoteUnavailable):
    # Not an error: Reeds doesn't serve this route. Tell your customer why.
    raise SystemExit(quote.reason.message)
print(quote.fee.total, quote.schedule)  # kobo, and the pickup and delivery promise

# 2. Book it. The wallet is charged and the delivery gets its tracking code.
delivery = reeds.shipping.deliveries.create(quote_id=quote.id, reference="ORDER-10045")

# 3. Follow it with webhooks (see below), or read it.
latest = reeds.shipping.deliveries.get(delivery.id)
print(latest.status, latest.tracking_url)
```

Parameters are keyword arguments, and field names are the API's own (`quote_id`, `tracking_code`), so your code reads like the [API reference](https://developer.getreeds.co/api). **Amounts are integers in kobo:** `280000` is ₦2,800. Times are ISO 8601 strings in Lagos time (`datetime.fromisoformat` reads them).

### Coverage and quotes

```python
coverage = reeds.shipping.coverage.get()  # the states, zones and inter-state routes Reeds serves
for state in coverage.states or []:
    print(state.state, state.zones)
```

A quote holds its price for 24 hours. A route Reeds doesn't serve comes back as a `QuoteUnavailable` (`available` is `False`) with a `reason` (`ADDRESS_NOT_SERVICEABLE`, `INTERSTATE_NOT_AVAILABLE`, ...), never as an error. Branch on `reason.code`, not the message.

### Address search

Complete an address as your customer types, or read one from a map pin, and give the quote the `lga`, `state` and `place_id` it needs. The addresses are Google's, in Nigeria. Call it from your server, as you do every call with your credentials.

```python
import uuid

from reeds.shipping import AddressInputParam

# One session token per address being typed. Send it on every call while your customer
# types that address, and on the details call: the whole search then counts as one.
session = str(uuid.uuid4())

found = reeds.shipping.addresses.autocomplete(query="23 Allen Avenue", session_token=session)
for suggestion in found.suggestions:  # at most 6, best first; empty when nothing matched
    print(suggestion.place_id, suggestion.main_text, suggestion.secondary_text)

# The suggestion your customer picks, with the same token: this ends the search.
place = reeds.shipping.addresses.details(place_id=found.suggestions[0].place_id, session_token=session)
if place.lga is None:
    raise ValueError("Ask your customer for the LGA: a quote needs it.")

pickup: AddressInputParam = {
    "name": "Tola Fabrics",
    "phone": "08051234567",
    "address": place.formatted_address,
    "lga": place.lga,
    "state": place.state,
    "place_id": place.place_id,  # the spot is then exact
}
if place.area:
    pickup["area"] = place.area
quote = reeds.shipping.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "2 pairs of sneakers", "quantity": 1, "weight_kg": 1.5})
```

`precise` is `False` for a whole area or road, whose point is only its middle: ask your customer for the street. For a map pin:

```python
pin = reeds.shipping.addresses.reverse(latitude=6.6018, longitude=3.3515)  # one search per pin
print(pin.formatted_address, pin.lga, pin.state, pin.place_id)
```

To deliver to the pin itself, send your pin's `latitude` and `longitude` in the quote, with this address as the text; to deliver to the address found, send its `place_id`. A pin outside Nigeria is an `InvalidRequestError`, and one with no address near it a `NotFoundError`.

Address search is free. Test mode has an allowance of 50 searches to start, which Reeds can raise; Live is unlimited unless Reeds sets a monthly limit for your account. Past it, a search raises `PermissionDeniedError` with the code `ADDRESS_SEARCH_LIMIT_REACHED`; if Reeds has switched address search off for your account, `ADDRESS_SEARCH_DISABLED`. A search you started can always finish. Google's rules apply to its addresses: show "Powered by Google" (or the Google logo) next to suggestions that aren't on a Google map, and show pins on a Google map. See the [address search guide](https://developer.getreeds.co/docs/shipping/address-search).

### Deliveries

| Method | What it does |
|---|---|
| `deliveries.create(quote_id=..., reference=..., ready=..., ...)` | Books the delivery a quote priced, and charges it |
| `deliveries.list(status=..., reference=..., ids=..., created_from=..., created_to=..., limit=...)` | Deliveries, newest first (see [pagination](#lists-and-pagination)) |
| `deliveries.get(id)` | One delivery |
| `deliveries.update(id, reference=..., pickup_instructions=..., dropoff_instructions=..., metadata=...)` | Changes what can change |
| `deliveries.mark_ready(id)` | The parcel is packed: the pickup is scheduled from now |
| `deliveries.cancel(id, reason=...)` | Cancels and refunds in full, until the rider sets off |
| `deliveries.book(id)` | Books a priced delivery your team made in the dashboard |
| `deliveries.label(id)` | The shipping label, as a PDF |

**Not packed yet?** Book with `ready=False`. The delivery is charged and gets its tracking code, then waits with a `MARK_READY` action:

```python
delivery = reeds.shipping.deliveries.create(quote_id=quote.id, ready=False)
# ...when the parcel is packed:
reeds.shipping.deliveries.mark_ready(delivery.id)  # now "scheduled", with its pickup and delivery times
```

A booked delivery that isn't marked ready within 7 days is cancelled and refunded in full.

### Delivery statuses

| Status | Meaning |
|---|---|
| `requires_action` | Waiting on you: `required_actions` says what (for example `MARK_READY`) |
| `scheduled` | Booked and charged, waiting for its pickup time and a rider |
| `rider_assigned` | A rider has the pickup |
| `picked_up` | Collected from the pickup address |
| `at_hub` | At a Reeds or partner hub |
| `in_transit` | Moving between hubs on an inter-state delivery |
| `out_for_delivery` | With the rider, heading to the receiver |
| `delivered` | Delivered. Final. |
| `failed_attempt` | The rider couldn't deliver. Reeds retries or contacts you. |
| `on_hold` | Paused by Reeds. `hold_reason` says why. |
| `cancelled` | Cancelled. Final. |

Reeds can add statuses: give every `match` on `status` a default case.

### Labels

```python
label = reeds.shipping.deliveries.label(delivery.id)
label.write_to(f"{delivery.id}.pdf")  # or a directory, to save it as label.filename
label.data, label.content_type  # the bytes, and "application/pdf"
```

### Wallet and invoices

```python
wallet = reeds.shipping.wallet.get()
print(wallet.balance)  # kobo

# Live mode: start a Paystack top-up (₦50,000) and send the payer to the URL.
# wallet.funded carries the same reference when the money lands.
top_up = reeds.shipping.wallet.fund(amount=5_000_000)
print(top_up.payment_url, top_up.reference)

for entry in reeds.shipping.wallet.list_transactions():
    print(entry.type, entry.amount, entry.description)

# Accounts billed monthly:
for invoice in reeds.shipping.invoices.list(status="issued"):
    if invoice.id:
        reeds.shipping.invoices.pdf(invoice.id).write_to(f"{invoice.number}.pdf")
```

### Test mode and the sandbox

With test credentials, build the whole flow without real money or riders:

```python
reeds.shipping.sandbox.fund_wallet(amount=1_000_000)  # ₦10,000 in the test wallet, at once
reeds.shipping.sandbox.advance_delivery(delivery.id)  # the next status, with its webhook
reeds.shipping.sandbox.advance_delivery(delivery.id, status="delivered")  # straight to a status
```

Sandbox calls are refused before anything is sent when the client has live credentials.

## Async

`AsyncReeds` has the same methods; await them. A list is awaited for one page, or walked with `async for`:

```python
import asyncio

from reeds import AsyncReeds
from reeds.shipping import Quote


async def main() -> None:
    async with AsyncReeds() as reeds:
        quote = await reeds.shipping.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "Sneakers"})
        if isinstance(quote, Quote):
            delivery = await reeds.shipping.deliveries.create(quote_id=quote.id)
            print(delivery.tracking_code)

        page = await reeds.shipping.deliveries.list(limit=50)  # await: one page
        print(len(page.data), page.has_more)
        async for delivery in reeds.shipping.deliveries.list(status="delivered"):  # async for: every delivery
            print(delivery.id)


asyncio.run(main())
```

Create one client and reuse it: it keeps one access token and one connection pool. `async with` (or `await reeds.close()`) closes the connections.

## Webhooks

Reeds posts events to your endpoint as things happen. Verify each one before you trust it: pass the **raw** request body, because a body that was decoded and encoded again never matches the signature. The signing secret (`whsec_test_...` or `whsec_live_...`) is next to your endpoint in **Dashboard → Developers**. It isn't your client secret.

`construct_event` checks the signature and returns a typed event. Match on its class:

```python
import os

from reeds import WebhookSignatureError, webhooks
from reeds.shipping import DeliveryStatusChangedEvent, WalletLowBalanceEvent


def handle(body: bytes, signature: str | None) -> int:
    try:
        event = webhooks.construct_event(body, signature, os.environ["REEDS_WEBHOOK_SECRET"])
    except WebhookSignatureError as error:
        print(error.message)
        return 400

    match event:
        case DeliveryStatusChangedEvent():
            print(event.data.delivery.id, event.data.previous_status, "->", event.data.delivery.status)
        case WalletLowBalanceEvent():
            print("Top up: the wallet is at", event.data.balance)
        case _:
            pass  # Reeds adds event types over time: ignore the ones you don't use
    return 200
```

`webhooks` verifies events without credentials; `Reeds().webhooks` does the same and can also send test events.

### FastAPI

`await request.body()` is the raw body:

```python
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
```

### Flask

`request.get_data()` is the raw body:

```python
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
```

### Django

`request.body` is the raw body. The view is exempt from CSRF: Reeds signs its requests instead. In your project the view goes in `views.py` and the route in `urls.py`:

```python
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
```

| Event | When |
|---|---|
| `delivery.created` | A delivery was created: booked from a quote, or made in the dashboard |
| `delivery.requires_action` | An action was added to `required_actions` |
| `delivery.booked` | The delivery was priced and charged (or added to the month's invoice) |
| `delivery.status_changed` | Any status change |
| `delivery.schedule_changed` | The pickup day or delivery time moved |
| `delivery.expiring` | A delivery will be cancelled soon if nothing happens |
| `delivery.cancelled` | The delivery was cancelled |
| `wallet.funded` | A top-up landed and the wallet was credited |
| `wallet.low_balance` | The balance fell to or below your low-balance threshold |
| `invoice.issued` | A monthly invoice was issued |
| `invoice.paid` | An invoice was paid in full |
| `invoice.overdue` | An invoice passed its due date unpaid |

Each has a model in `reeds.shipping` (`DeliveryBookedEvent`, `WalletFundedEvent`, ...). An event type this version doesn't know yet arrives as an `UnknownEvent`, so a new type never breaks your endpoint.

Good to know:
- **Duplicates:** an event can arrive more than once. Skip `event.id`s you've already processed.
- **Order:** events can arrive out of order. Compare `event.data.delivery.updated_at`.
- **Rotating a secret:** pass both while you rotate, as `construct_event(body, signature, [new_secret, old_secret])`.
- **Testing your receiver:** send a signed test event to your endpoint:

```python
reeds.webhooks.send_test(type="delivery.booked")
```

## Lists and pagination

A list returns its first page, and iterating it walks every item, fetching pages as you go:

```python
page = reeds.shipping.deliveries.list(status="delivered", limit=50)
page.data  # up to 50, newest first
page.has_more  # True when another page follows
page.next_page()  # the next page, or None

for delivery in reeds.shipping.deliveries.list(status="delivered"):
    ...  # every delivered delivery; pages are fetched as you go
```

With `AsyncReeds`, `await` the list for its first page and `await page.next_page()`, or `async for` over it for every item ([async](#async)).

## Errors

Every failure raises a `ReedsError` subclass. Branch on the class or on `error.code`, never on the message, which Reeds can reword.

```python
from reeds import InvalidRequestError, PaymentRequiredError, ReedsError

try:
    reeds.shipping.deliveries.create(quote_id=quote.id)
except PaymentRequiredError:
    ...  # INSUFFICIENT_BALANCE: top up, then retry with the same idempotency_key
except InvalidRequestError as error:
    print(error.fields)  # [{"field": "dropoff.lga", "message": "Enter the LGA."}]
except ReedsError as error:
    print(error.code, error.message, error.request_id, error.doc_url)
    raise
```

| Class | Status | Typical codes |
|---|---|---|
| `AuthenticationError` | 401, or wrong or missing credentials | `TOKEN_EXPIRED`, `invalid_client`, `MISSING_CREDENTIALS` |
| `PermissionDeniedError` | 403 | `INSUFFICIENT_SCOPE`, `IP_NOT_ALLOWED`, `TEST_MODE_ONLY`, `ACCOUNT_ON_HOLD`, `ADDRESS_SEARCH_LIMIT_REACHED`, `ADDRESS_SEARCH_DISABLED` |
| `NotFoundError` | 404 | `NOT_FOUND` |
| `ConflictError` | 409 | `ACTION_NOT_ALLOWED`, `QUOTE_ALREADY_USED`, `QUOTE_EXPIRED`, `CANCEL_NOT_ALLOWED` |
| `InvalidRequestError` | 400, 422 | `INVALID_REQUEST` (see `fields`), `IDEMPOTENCY_KEY_REQUIRED` |
| `PaymentRequiredError` | 402 | `INSUFFICIENT_BALANCE`, `CREDIT_LIMIT_REACHED` |
| `RateLimitError` | 429 | `RATE_LIMITED` (`retry_after` in seconds) |
| `ServiceUnavailableError` | 503 | `SERVICE_UNAVAILABLE` (`retry_after` in seconds) |
| `APIError` | other 5xx, or a response the library doesn't recognise | `INTERNAL_ERROR`, `UNEXPECTED_RESPONSE` |
| `APIConnectionError`, `APIConnectionTimeoutError` | no response | `CONNECTION_FAILED`, `TIMEOUT` |
| `WebhookSignatureError` | a webhook that doesn't verify | `SIGNATURE_MISMATCH`, `TIMESTAMP_OUTSIDE_TOLERANCE`, `RAW_BODY_REQUIRED` |

Every error has:
- `status`, `code` and `message`;
- `fields`: what to fix, on validation errors;
- `doc_url`: the code's page on the developer hub;
- `request_id`: quote it to support;
- `raw`: the API's error object, including fields some codes add, such as `delivery_id` on `QUOTE_ALREADY_USED`.

## Retries, idempotency and timeouts

| Retried (up to `max_retries`, default 2) | Never retried |
|---|---|
| No response (network error, timeout) | `400`, `401`*, `402`, `403`, `404`, `409`, `422` |
| `429`, `502`, `503`, `504`, waiting for `Retry-After` (at most 30 s) | |
| `500` on a `GET` | |
| `409 REQUEST_IN_PROGRESS` (the same key still running) | |

\* An expired token is refreshed once and the request sent again, automatically.

Waits back off from about half a second, up to 8 seconds. Every `POST` carries an `Idempotency-Key`, and a retry sends the same one, so Reeds acts on it once. To make your own retries safe too (after a crash, or a deploy), pass a key tied to your order:

```python
reeds.shipping.deliveries.create(quote_id=quote.id, reference="ORDER-10045", idempotency_key="order-10045-delivery")
```

Every method also takes `timeout` (seconds), `max_retries` and `extra_headers`, for that request only:

```python
reeds.shipping.deliveries.list(limit=10, timeout=10, max_retries=0)
```

## Types

The models and parameter types follow the API's OpenAPI spec. Import them from `reeds.shipping`:

```python
from reeds.shipping import Delivery, DeliveryStatus


def is_done(delivery: Delivery) -> bool:
    final: list[DeliveryStatus] = ["delivered", "cancelled"]
    return delivery.status in final
```

Parameters are TypedDicts, so a dict you build ahead is checked too:

```python
from reeds.shipping import AddressInputParam

pickup: AddressInputParam = {"name": "Tola Fabrics", "phone": "08051234567", "address": "23 Allen Avenue", "lga": "Ikeja", "state": "Lagos"}
```

The types accept values Reeds adds later: an enum such as `DeliveryStatus` is its known values or any string, so a new status type-checks and parses. Fields Reeds adds are kept on the model:

```python
print(delivery.to_dict())  # the API's JSON, including fields this version doesn't know
delivery.model_extra  # just the fields this version doesn't know
```

An object that doesn't fit its model (a field missing, a value of another type) never raises: the library keeps what came, so a call that charged never looks like it failed.

## Configuration

```python
import httpx2

from reeds import Reeds

reeds = Reeds(
    client_id="rci_test_...",  # default: REEDS_CLIENT_ID
    client_secret="rcs_test_...",  # default: REEDS_CLIENT_SECRET
    base_url="https://api.getreeds.co",  # the default
    timeout=60,  # seconds per attempt
    max_retries=2,
    default_headers={"X-Your-Header": "value"},
    http_client=httpx2.Client(proxy="http://proxy.internal:8080"),  # proxies, custom TLS
)

with Reeds() as reeds:  # closes its connections at the end
    reeds.shipping.coverage.get()
```

`AsyncReeds` takes the same options, with an `httpx2.AsyncClient` as `http_client`. A client you pass in stays open: close it yourself.

## Versioning

The library follows [semantic versioning](https://semver.org). Until 1.0.0, a minor version may change something you use: read the [changelog](CHANGELOG.md) before upgrading.

Within an API version (`v1`), Reeds adds fields, statuses and event types without notice. The library keeps them rather than dropping them, and its types allow them.

Every release is built by GitHub Actions and published to PyPI with [trusted publishing](https://docs.pypi.org/trusted-publishers/), with no long-lived token.

## Support

- **Docs and guides:** [developer.getreeds.co](https://developer.getreeds.co).
- **Help with a call:** email support@getreeds.co with the `request_id` from the error (or the `X-Request-Id` header). Every call is also listed in Dashboard → Developers → API requests for 30 days.
- **A bug in the library:** [open an issue](https://github.com/SendX-hq/reeds-python/issues).
- **A security problem:** email support@getreeds.co rather than opening an issue.

## License

[MIT](LICENSE) © Reeds Merchants Technologies Ltd.
