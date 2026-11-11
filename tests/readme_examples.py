"""Every Python example in README.md, type-checked by mypy --strict and pyright
(strict) in CI, never run. tests/test_readme.py fails when a README block isn't
here word for word, so the README can't drift from code that type-checks. The
webhook handlers for FastAPI, Flask and Django live in tests/frameworks/, where
they run in real apps."""

# ruff: noqa: B007, B018, F811, F841
from __future__ import annotations

from reeds import shipping


def hero(pickup: shipping.AddressInputParam, dropoff: shipping.AddressInputParam) -> None:
    from reeds import Reeds
    from reeds.shipping import Quote

    reeds = Reeds()  # reads REEDS_CLIENT_ID and REEDS_CLIENT_SECRET

    quote = reeds.shipping.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "Sneakers", "quantity": 1, "weight_kg": 1.5})
    if isinstance(quote, Quote):
        delivery = reeds.shipping.deliveries.create(quote_id=quote.id, reference="ORDER-10045")
        print(delivery.tracking_code)  # HQ3W5F2


def credentials() -> None:
    import os

    from reeds import Reeds

    reeds = Reeds(client_id=os.environ["REEDS_CLIENT_ID"], client_secret=os.environ["REEDS_CLIENT_SECRET"])

    reeds.mode  # "test" or "live", from the client id
    reeds.scopes()  # the services your credentials can use, for example ["shipping"]


def quickstart() -> None:
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

    coverage = reeds.shipping.coverage.get()  # the states, zones and inter-state routes Reeds serves
    for state in coverage.states or []:
        print(state.state, state.zones)

    delivery = reeds.shipping.deliveries.create(quote_id=quote.id, ready=False)
    # ...when the parcel is packed:
    reeds.shipping.deliveries.mark_ready(delivery.id)  # now "scheduled", with its pickup and delivery times

    label = reeds.shipping.deliveries.label(delivery.id)
    label.write_to(f"{delivery.id}.pdf")  # or a directory, to save it as label.filename
    label.data, label.content_type  # the bytes, and "application/pdf"

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

    reeds.shipping.sandbox.fund_wallet(amount=1_000_000)  # ₦10,000 in the test wallet, at once
    reeds.shipping.sandbox.advance_delivery(delivery.id)  # the next status, with its webhook
    reeds.shipping.sandbox.advance_delivery(delivery.id, status="delivered")  # straight to a status

    page = reeds.shipping.deliveries.list(status="delivered", limit=50)
    page.data  # up to 50, newest first
    page.has_more  # True when another page follows
    page.next_page()  # the next page, or None

    for delivery in reeds.shipping.deliveries.list(status="delivered"):
        ...  # every delivered delivery; pages are fetched as you go

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

    reeds.shipping.deliveries.create(quote_id=quote.id, reference="ORDER-10045", idempotency_key="order-10045-delivery")

    reeds.shipping.deliveries.list(limit=10, timeout=10, max_retries=0)

    print(delivery.to_dict())  # the API's JSON, including fields this version doesn't know
    delivery.model_extra  # just the fields this version doesn't know

    reeds.webhooks.send_test(type="delivery.booked")


def address_search(dropoff: shipping.AddressInputParam) -> None:
    from reeds import Reeds

    reeds = Reeds()

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

    pin = reeds.shipping.addresses.reverse(latitude=6.6018, longitude=3.3515)  # one search per pin
    print(pin.formatted_address, pin.lga, pin.state, pin.place_id)


def async_usage(pickup: shipping.AddressInputParam, dropoff: shipping.AddressInputParam) -> None:
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


def plain_webhooks() -> None:
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

    body, signature, new_secret, old_secret = b"", "", "", ""
    event = webhooks.construct_event(body, signature, [new_secret, old_secret])


def types() -> None:
    from reeds.shipping import Delivery, DeliveryStatus

    def is_done(delivery: Delivery) -> bool:
        final: list[DeliveryStatus] = ["delivered", "cancelled"]
        return delivery.status in final

    from reeds.shipping import AddressInputParam

    pickup: AddressInputParam = {"name": "Tola Fabrics", "phone": "08051234567", "address": "23 Allen Avenue", "lga": "Ikeja", "state": "Lagos"}


def configuration() -> None:
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
