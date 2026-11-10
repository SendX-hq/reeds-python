"""The library against the real API in Test mode: run nightly by
.github/workflows/e2e.yml, or by hand. Needs TEST credentials of a dedicated account:

    REEDS_E2E_CLIENT_ID=rci_test_... REEDS_E2E_CLIENT_SECRET=rcs_test_... pytest tests/e2e

REEDS_E2E_BASE_URL picks the API (default https://api.getreeds.co). Test mode
never moves real money or sends a rider. Without credentials the tests skip,
unless REEDS_E2E_REQUIRED is set (CI), when they fail: a skipped run proves nothing.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from reeds import AsyncReeds, ConflictError, NotFoundError, Reeds
from reeds.shipping import AddressInputParam, PackageParam, Quote

pytestmark = [pytest.mark.e2e, pytest.mark.anyio]

CLIENT_ID = os.environ.get("REEDS_E2E_CLIENT_ID")
CLIENT_SECRET = os.environ.get("REEDS_E2E_CLIENT_SECRET")
BASE_URL = os.environ.get("REEDS_E2E_BASE_URL") or None

PICKUP: AddressInputParam = {"name": "Reeds SDK test", "phone": "08031234567", "address": "23 Allen Avenue", "area": "Ikeja", "lga": "Ikeja", "state": "Lagos"}
DROPOFF: AddressInputParam = {
    "name": "Reeds SDK receiver",
    "phone": "08098765432",
    "address": "14 Admiralty Way",
    "area": "Lekki Phase 1",
    "lga": "Eti-Osa",
    "state": "Lagos",
}
PACKAGE: PackageParam = {"description": "SDK end-to-end test parcel", "quantity": 1, "weight_kg": 1}


@pytest.fixture(autouse=True)
def credentials() -> None:
    if not (CLIENT_ID and CLIENT_SECRET):
        if os.environ.get("REEDS_E2E_REQUIRED"):
            pytest.fail("REEDS_E2E_CLIENT_ID and REEDS_E2E_CLIENT_SECRET aren't set")
        pytest.skip("no Test-mode credentials (REEDS_E2E_CLIENT_ID, REEDS_E2E_CLIENT_SECRET)")


@pytest.fixture
def reeds() -> Iterator[Reeds]:
    with Reeds(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, base_url=BASE_URL) as client:
        yield client


def test_uses_test_credentials(reeds: Reeds) -> None:
    assert reeds.mode == "test"
    assert "shipping" in reeds.scopes()


def test_quote_book_not_ready_mark_ready_advance_to_delivered_label(reeds: Reeds) -> None:
    reeds.shipping.sandbox.fund_wallet(amount=1_000_000)
    quote = reeds.shipping.quotes.create(pickup=PICKUP, dropoff=DROPOFF, package=PACKAGE)
    assert isinstance(quote, Quote), f"Reeds didn't quote the test route: {quote.to_dict()}"

    reference = f"SDK-E2E-PY-{int(time.time() * 1000)}"
    made = reeds.shipping.deliveries.create(quote_id=quote.id, reference=reference, ready=False)
    assert made.status == "requires_action"
    assert [action.type for action in made.required_actions] == ["MARK_READY"]

    ready = reeds.shipping.deliveries.mark_ready(made.id)
    assert ready.status == "scheduled"

    delivered = reeds.shipping.sandbox.advance_delivery(made.id, status="delivered")
    assert delivered.status == "delivered"

    found = reeds.shipping.deliveries.list(reference=reference)
    assert [d.id for d in found.data] == [made.id]

    label = reeds.shipping.deliveries.label(made.id)
    assert label.data[:4] == b"%PDF"


def test_errors_carry_the_apis_code_and_request_id(reeds: Reeds) -> None:
    with pytest.raises(NotFoundError) as missing:
        reeds.shipping.deliveries.get("dlv_00000000-0000-0000-0000-000000000000")
    assert missing.value.request_id

    quote = reeds.shipping.quotes.create(pickup=PICKUP, dropoff=DROPOFF, package=PACKAGE)
    assert isinstance(quote, Quote)
    made = reeds.shipping.deliveries.create(quote_id=quote.id, ready=False)
    reeds.shipping.deliveries.cancel(made.id, reason="SDK end-to-end test")
    with pytest.raises(ConflictError):
        reeds.shipping.deliveries.mark_ready(made.id)


async def test_the_async_client_end_to_end() -> None:
    async with AsyncReeds(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, base_url=BASE_URL) as reeds:
        assert "shipping" in await reeds.scopes()
        await reeds.shipping.sandbox.fund_wallet(amount=1_000_000)
        quote = await reeds.shipping.quotes.create(pickup=PICKUP, dropoff=DROPOFF, package=PACKAGE)
        assert isinstance(quote, Quote)
        reference = f"SDK-E2E-PY-ASYNC-{int(time.time() * 1000)}"
        made = await reeds.shipping.deliveries.create(quote_id=quote.id, reference=reference, ready=False)
        assert (await reeds.shipping.deliveries.mark_ready(made.id)).status == "scheduled"
        assert (await reeds.shipping.sandbox.advance_delivery(made.id, status="delivered")).status == "delivered"
        assert [d.id async for d in reeds.shipping.deliveries.list(reference=reference)] == [made.id]
        assert (await reeds.shipping.deliveries.label(made.id)).data[:4] == b"%PDF"
