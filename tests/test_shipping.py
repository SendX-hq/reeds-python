"""reeds.shipping on both clients: every operation's request, lists, files, the sandbox."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest

from reeds import AsyncPage, FileResponse, Page, PermissionDeniedError
from reeds.shipping import Place, PlaceSuggestionsResult, Quote, QuoteUnavailable

from .helpers import Call, catch, collect, delivery, failure, json_response, run, success

pytestmark = pytest.mark.anyio

pickup = {"name": "Tola Fabrics", "phone": "08051234567", "address": "23 Allen Avenue", "lga": "Ikeja", "state": "Lagos"}
dropoff = {"name": "Chinedu Eze", "phone": "08098765432", "address": "14 Admiralty Way", "lga": "Eti-Osa", "state": "Lagos"}


def pdf(_call: Call) -> httpx2.Response:
    return httpx2.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})


async def test_sends_each_call_to_its_path_with_its_method_body_and_query(fake: Any) -> None:
    def answer(call: Call) -> httpx2.Response:
        if call.url.path.endswith(("/label", "/pdf")):
            return pdf(call)
        if call.method == "GET" and re.search(r"/(deliveries|transactions|invoices)$", call.url.path):
            return json_response(200, {"status": "success", "data": [], "has_more": False})
        return success({"id": "x"})

    api = fake(answer)
    client = api.client()
    s = client.shipping
    await run(s.coverage.get())
    await run(s.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "Shoes", "weight_kg": 2}))
    await run(s.deliveries.create(quote_id="qt_1", reference="ORDER-1", ready=False))
    await run(s.deliveries.list(status="scheduled", ids=["dlv_1", "dlv_2"], limit=10))
    await run(s.deliveries.get("dlv_1"))
    await run(s.deliveries.update("dlv_1", reference="ORDER-2"))
    await run(s.deliveries.book("dlv_1"))
    await run(s.deliveries.mark_ready("dlv_1"))
    await run(s.deliveries.cancel("dlv_1", reason="Customer cancelled"))
    await run(s.deliveries.label("dlv_1"))
    await run(s.wallet.get())
    await run(s.wallet.fund(amount=500000))
    await run(s.wallet.list_transactions(limit=5))
    await run(s.invoices.list(status="issued"))
    await run(s.invoices.get("inv_1"))
    await run(s.invoices.pdf("inv_1"))
    await run(s.sandbox.fund_wallet(amount=1000000))
    await run(s.sandbox.advance_delivery("dlv_1", status="delivered"))
    await run(client.webhooks.send_test(type="delivery.booked"))

    seen = [f"{c.method} {c.url.raw_path.decode()}" + (f" {c.body}" if c.body else "") for c in api.api_calls()]
    quote_body = json.dumps({"pickup": pickup, "dropoff": dropoff, "package": {"description": "Shoes", "weight_kg": 2}}, separators=(",", ":"))
    assert seen == [
        "GET /shipping/v1/coverage",
        f"POST /shipping/v1/quotes {quote_body}",
        'POST /shipping/v1/deliveries {"quote_id":"qt_1","reference":"ORDER-1","ready":false}',
        "GET /shipping/v1/deliveries?status=scheduled&ids=dlv_1%2Cdlv_2&limit=10",
        "GET /shipping/v1/deliveries/dlv_1",
        'PATCH /shipping/v1/deliveries/dlv_1 {"reference":"ORDER-2"}',
        "POST /shipping/v1/deliveries/dlv_1/book",
        "POST /shipping/v1/deliveries/dlv_1/ready",
        'POST /shipping/v1/deliveries/dlv_1/cancel {"reason":"Customer cancelled"}',
        "GET /shipping/v1/deliveries/dlv_1/label",
        "GET /shipping/v1/wallet",
        'POST /shipping/v1/wallet/fund {"amount":500000}',
        "GET /shipping/v1/wallet/transactions?limit=5",
        "GET /shipping/v1/invoices?status=issued",
        "GET /shipping/v1/invoices/inv_1",
        "GET /shipping/v1/invoices/inv_1/pdf",
        'POST /shipping/v1/sandbox/wallet/fund {"amount":1000000}',
        'POST /shipping/v1/sandbox/deliveries/dlv_1/advance {"status":"delivered"}',
        'POST /shipping/v1/webhooks/test {"type":"delivery.booked"}',
    ]
    label = next(c for c in api.api_calls() if c.url.path.endswith("/label"))
    assert label.headers["accept"] == "application/pdf"


async def test_a_cancel_without_a_reason_sends_an_empty_object(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1")))
    await run(api.client().shipping.deliveries.cancel("dlv_1"))
    assert api.api_calls()[0].body == "{}"
    assert api.api_calls()[0].headers["content-type"] == "application/json"


async def test_escapes_ids_in_the_path(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1")))
    await run(api.client().shipping.deliveries.get("dlv_1/../wallet"))
    assert api.api_calls()[0].url.raw_path.decode() == "/shipping/v1/deliveries/dlv_1%2F..%2Fwallet"


# ------------------------------------------------------------ quotes


async def test_a_quote_comes_back_as_a_quote(fake: Any) -> None:
    quote = {
        "id": "qt_1",
        "available": True,
        "livemode": False,
        "expires_at": "2026-11-10T10:20:00+01:00",
        "service": "standard",
        "route": {"type": "direct", "distance_km": 4.2},
        "fee": {"delivery_fee": 250000, "vat": 18750, "service_charge": 11250, "discount": 0, "total": 280000, "currency": "NGN"},
        "schedule": {"pickup_by": "2026-11-10", "deliver_by": "2026-11-12T17:00:00+01:00"},
        "package": {"description": "Shoes"},
    }
    api = fake(lambda call: success(quote, 201))
    result = await run(api.client().shipping.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "Shoes"}))
    assert isinstance(result, Quote)
    assert (result.id, result.fee.total, result.route.distance_km) == ("qt_1", 280000, 4.2)


async def test_a_route_reeds_doesnt_serve_is_available_false_not_an_error(fake: Any) -> None:
    reason = {"code": "INTERSTATE_NOT_AVAILABLE", "message": "Reeds doesn't deliver from Lagos to Kano."}
    api = fake(lambda call: success({"available": False, "reason": reason}))
    result = await run(api.client().shipping.quotes.create(pickup=pickup, dropoff=dropoff, package={"description": "Shoes"}))
    assert isinstance(result, QuoteUnavailable)
    assert result.available is False
    assert result.reason.code == "INTERSTATE_NOT_AVAILABLE"


# ------------------------------------------------------------ address search

TOKEN = "3f2c8d1e-7b4a-4c55-9e0d-2a6b1f9c8e70"
allen = {
    "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
    "name": "23 Allen Avenue",
    "formatted_address": "23 Allen Ave, Allen, Ikeja 101233, Lagos, Nigeria",
    "area": "Ikeja",
    "lga": "Ikeja",
    "state": "Lagos",
    "country": "NG",
    "latitude": 6.6018,
    "longitude": 3.3515,
    "precise": True,
}


async def test_address_search_sends_each_call_as_a_get_with_its_query(fake: Any) -> None:
    def answer(call: Call) -> httpx2.Response:
        return success({"suggestions": []}) if call.url.path.endswith("/autocomplete") else success(allen)

    api = fake(answer)
    addresses = api.client().shipping.addresses
    await run(addresses.autocomplete(query="23 Allen Avenue", session_token=TOKEN))
    await run(addresses.details(place_id=allen["place_id"], session_token=TOKEN))
    await run(addresses.details(place_id=allen["place_id"]))
    await run(addresses.reverse(latitude=6.6018, longitude=3.3515))
    await run(addresses.reverse(latitude=4.00001, longitude=1e-05))

    calls = api.api_calls()
    assert [f"{c.method} {c.url.path}" for c in calls] == [
        "GET /shipping/v1/addresses/autocomplete",
        "GET /shipping/v1/addresses/details",
        "GET /shipping/v1/addresses/details",
        "GET /shipping/v1/addresses/reverse",
        "GET /shipping/v1/addresses/reverse",
    ]
    assert [dict(c.url.params) for c in calls] == [
        {"query": "23 Allen Avenue", "session_token": TOKEN},
        {"place_id": allen["place_id"], "session_token": TOKEN},
        {"place_id": allen["place_id"]},  # no token: the place is a search of its own
        {"latitude": "6.6018", "longitude": "3.3515"},
        {"latitude": "4.00001", "longitude": "0.00001"},  # plain decimals, never 1e-05
    ]
    assert all(c.body is None and "idempotency-key" not in c.headers for c in calls)


async def test_suggestions_and_places_come_back_as_models(fake: Any) -> None:
    suggestions = [
        {"place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4", "main_text": "23 Allen Avenue", "secondary_text": "Ikeja, Lagos, Nigeria"},
        {"place_id": "ChIJ8TQy0JKLOxARmZ9bJc2sVkA", "main_text": "Allen Avenue Roundabout", "secondary_text": ""},
    ]

    def answer(call: Call) -> httpx2.Response:
        if call.url.path.endswith("/autocomplete"):
            return success({"suggestions": suggestions})
        return success({**allen, "lga": None, "precise": False} if call.url.path.endswith("/reverse") else allen)

    addresses = fake(answer).client().shipping.addresses
    found = await run(addresses.autocomplete(query="Allen", session_token=TOKEN))
    assert isinstance(found, PlaceSuggestionsResult)
    assert [(s.place_id, s.main_text, s.secondary_text) for s in found.suggestions] == [tuple(s.values()) for s in suggestions]

    place = await run(addresses.details(place_id=allen["place_id"], session_token=TOKEN))
    assert isinstance(place, Place)
    assert (place.formatted_address, place.area, place.lga, place.state, place.country) == (allen["formatted_address"], "Ikeja", "Ikeja", "Lagos", "NG")
    assert (place.latitude, place.longitude, place.precise) == (6.6018, 3.3515, True)

    pin = await run(addresses.reverse(latitude=6.6018, longitude=3.3515))
    assert isinstance(pin, Place)
    assert (pin.lga, pin.precise) == (None, False)


async def test_address_search_past_the_allowance_or_switched_off_is_permission_denied(fake: Any) -> None:
    for code in ("ADDRESS_SEARCH_LIMIT_REACHED", "ADDRESS_SEARCH_DISABLED"):
        api = fake(lambda call, code=code: failure(403, code, "No more address searches."))
        error = await catch(lambda api=api: api.client().shipping.addresses.autocomplete(query="Allen", session_token=TOKEN))
        assert isinstance(error, PermissionDeniedError)
        assert (error.status, error.code, error.doc_url) == (403, code, f"https://developer.getreeds.co/errors/{code}")
        assert len(api.api_calls()) == 1  # a 403 is never retried


# ------------------------------------------------------------ lists


def pages(fake: Any, ids: list[list[str]]) -> Any:
    def answer(call: Call) -> httpx2.Response:
        after = call.url.params.get("starting_after")
        index = 0 if after is None else next(i for i, page in enumerate(ids) if page and page[-1] == after) + 1
        page = ids[index] if index < len(ids) else []
        return json_response(200, {"status": "success", "data": [delivery(i) for i in page], "has_more": index < len(ids) - 1})

    return fake(answer)


async def test_the_first_page_has_data_has_more_and_next_page(fake: Any, flavour: str) -> None:
    api = pages(fake, [["dlv_3", "dlv_2"], ["dlv_1"]])
    page = await run(api.client().shipping.deliveries.list(limit=2))
    assert isinstance(page, Page if flavour == "sync" else AsyncPage)
    assert [d.id for d in page.data] == ["dlv_3", "dlv_2"]
    assert page.has_more is True
    following = await run(page.next_page())
    assert [d.id for d in following.data] == ["dlv_1"]
    assert following.has_more is False
    assert await run(following.next_page()) is None
    assert api.api_calls()[1].url.raw_path.decode().endswith("?limit=2&starting_after=dlv_2")


async def test_iterating_walks_every_page_keeping_the_filters(fake: Any) -> None:
    api = pages(fake, [["dlv_5", "dlv_4"], ["dlv_3", "dlv_2"], ["dlv_1"]])
    items = await collect(api.client().shipping.deliveries.list(status="delivered", limit=2))
    assert [d.id for d in items] == ["dlv_5", "dlv_4", "dlv_3", "dlv_2", "dlv_1"]
    assert [c.url.params.get("starting_after") for c in api.api_calls()] == [None, "dlv_4", "dlv_2"]
    assert all(c.url.params.get("status") == "delivered" for c in api.api_calls())


async def test_iterating_a_page_you_already_have_starts_from_it(fake: Any) -> None:
    api = pages(fake, [["dlv_3", "dlv_2"], ["dlv_1"]])
    page = await run(api.client().shipping.deliveries.list(limit=2))
    assert [d.id for d in await collect(page)] == ["dlv_3", "dlv_2", "dlv_1"]


async def test_an_empty_list_ends_at_once(fake: Any) -> None:
    api = pages(fake, [[]])
    assert await collect(api.client().shipping.wallet.list_transactions()) == []
    assert len(api.api_calls()) == 1


# ------------------------------------------------------------ files


async def test_returns_a_labels_bytes_type_and_filename(fake: Any, tmp_path: Path) -> None:
    api = fake(
        lambda call: httpx2.Response(
            200, content=b"%PDF-1.7 label", headers={"content-type": "application/pdf", "content-disposition": 'inline; filename="reeds-label-HQ3W5F2.pdf"'}
        )
    )
    file = await run(api.client().shipping.deliveries.label("dlv_1"))
    assert isinstance(file, FileResponse)
    assert (file.filename, file.content_type, file.data) == ("reeds-label-HQ3W5F2.pdf", "application/pdf", b"%PDF-1.7 label")
    assert file.write_to(tmp_path) == tmp_path / "reeds-label-HQ3W5F2.pdf"
    assert (tmp_path / "reeds-label-HQ3W5F2.pdf").read_bytes() == b"%PDF-1.7 label"
    assert file.write_to(tmp_path / "mine.pdf").read_bytes() == b"%PDF-1.7 label"


def test_a_suggested_filename_never_picks_the_directory(tmp_path: Path) -> None:
    file = FileResponse(data=b"%PDF", content_type="application/pdf", filename="../../etc/passwd")
    assert file.write_to(tmp_path) == tmp_path / "passwd"
    assert FileResponse(data=b"%PDF", content_type="application/pdf", filename="..").write_to(tmp_path) == tmp_path / "download.pdf"


async def test_reads_an_encoded_filename(fake: Any) -> None:
    api = fake(lambda call: httpx2.Response(200, content=b"%PDF", headers={"content-disposition": "attachment; filename*=UTF-8''invoice%20RDS-2026.pdf"}))
    file = await run(api.client().shipping.invoices.pdf("inv_1"))
    assert file.filename == "invoice RDS-2026.pdf"


# ------------------------------------------------------------ the sandbox


async def test_the_sandbox_refuses_live_credentials_before_sending_anything(fake: Any) -> None:
    api = fake(lambda call: success({}))
    client = api.client(client_id="rci_live_abc", client_secret="rcs_live_xyz")
    for call in (lambda: client.shipping.sandbox.fund_wallet(amount=1000), lambda: client.shipping.sandbox.advance_delivery("dlv_1")):
        error = await catch(call)
        assert isinstance(error, PermissionDeniedError)
        assert error.code == "TEST_MODE_ONLY"
    assert api.calls == []
