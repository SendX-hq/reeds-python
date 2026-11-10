"""The core, on both clients: credentials and the token, requests, retries, errors."""

from __future__ import annotations

import asyncio
import json
import platform
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
from typing import Any

import httpx
import pytest

import reeds
from reeds import (
    APIConnectionError,
    APIConnectionTimeoutError,
    APIError,
    AsyncReeds,
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    Reeds,
    ReedsError,
    ServiceUnavailableError,
)
from reeds.shipping import Delivery

from .helpers import catch, delivery, failure, json_response, run, sequence, success, token_response

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------ credentials and the token


async def test_fetches_one_token_form_encoded_and_reuses_it(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1")))
    client = api.client()
    await run(client.shipping.deliveries.get("dlv_1"))
    await run(client.shipping.deliveries.get("dlv_1"))
    assert len(api.token_calls()) == 1
    token = api.token_calls()[0]
    assert str(token.url) == "https://api.getreeds.co/oauth/token"
    assert token.headers["content-type"] == "application/x-www-form-urlencoded"
    assert token.form == {"grant_type": "client_credentials", "client_id": "rci_test_abc", "client_secret": "rcs_test_xyz"}
    assert "idempotency-key" not in token.headers
    assert all(call.headers["authorization"] == "Bearer tok_1" for call in api.api_calls())


async def test_concurrent_first_calls_share_one_token_request(fake: Any, flavour: str) -> None:
    api = fake(lambda call: success(delivery("dlv_1")), token_delay=0.05)
    client = api.client()
    if flavour == "async":
        await asyncio.gather(*(client.shipping.deliveries.get("dlv_1") for _ in range(5)))
    else:
        with ThreadPoolExecutor(5) as pool:
            list(pool.map(lambda _: client.shipping.deliveries.get("dlv_1"), range(5)))
    assert len(api.token_calls()) == 1
    assert len(api.api_calls()) == 5


async def test_refreshes_a_token_a_minute_before_it_expires(fake: Any) -> None:
    tokens = iter(f"tok_{n}" for n in range(1, 10))
    api = fake(lambda call: success(delivery("dlv_1")), lambda: token_response(next(tokens)))
    client = api.client()
    start = api.now
    await run(client.shipping.deliveries.get("dlv_1"))
    api.now = start + 58 * 60
    await run(client.shipping.deliveries.get("dlv_1"))
    assert len(api.token_calls()) == 1
    api.now = start + 59 * 60 + 30
    await run(client.shipping.deliveries.get("dlv_1"))
    assert len(api.token_calls()) == 2
    assert api.api_calls()[-1].headers["authorization"] == "Bearer tok_2"


async def test_an_expired_token_gets_one_fresh_token_and_one_more_try_not_counted_as_a_retry(fake: Any) -> None:
    tokens = iter(f"tok_{n}" for n in range(1, 10))
    api = fake(sequence(failure(401, "TOKEN_EXPIRED", "The access token has expired."), success(delivery("dlv_1"))), lambda: token_response(next(tokens)))
    found = await run(api.client(max_retries=0).shipping.deliveries.get("dlv_1"))
    assert found.id == "dlv_1"
    assert [call.headers["authorization"] for call in api.api_calls()] == ["Bearer tok_1", "Bearer tok_2"]


async def test_a_second_401_in_a_row_is_an_authentication_error(fake: Any) -> None:
    api = fake(lambda call: failure(401, "UNAUTHENTICATED", "The access token isn't valid."))
    client = api.client()
    error = await catch(lambda: client.shipping.deliveries.get("dlv_1"))
    assert isinstance(error, AuthenticationError)
    assert len(api.api_calls()) == 2
    assert len(api.token_calls()) == 2


async def test_credentials_the_token_endpoint_refuses_are_an_authentication_error_with_the_oauth_code(fake: Any) -> None:
    api = fake(lambda call: success({}), lambda: json_response(401, {"error": "invalid_client", "error_description": "The client id or secret is wrong."}))
    client = api.client()
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, AuthenticationError)
    assert (error.status, error.code, error.message, error.request_id) == (401, "invalid_client", "The client id or secret is wrong.", "req_8h2KdP")
    assert api.api_calls() == []


async def test_without_credentials_a_call_says_where_to_find_them_and_webhooks_still_work(fake: Any) -> None:
    api = fake(lambda call: success({}))
    client = api.client(client_id=None, client_secret=None)
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, AuthenticationError)
    assert error.code == "MISSING_CREDENTIALS"
    assert "REEDS_CLIENT_ID" in error.message
    assert client.mode is None
    assert api.calls == []
    assert callable(client.webhooks.construct_event)


async def test_reads_the_environment_and_the_mode_from_the_client_id(fake: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REEDS_CLIENT_ID", "rci_live_envid")
    monkeypatch.setenv("REEDS_CLIENT_SECRET", "rcs_live_envsecret")
    api = fake(lambda call: success({}))
    client = api.client(client_id=None, client_secret=None)
    assert client.mode == "live"
    await run(client.shipping.coverage.get())
    assert api.token_calls()[0].form["client_id"] == "rci_live_envid"
    assert api.client().mode == "test"


async def test_scopes_lists_what_the_token_carries(fake: Any) -> None:
    api = fake(lambda call: success({}), lambda: token_response("tok_1", scope="shipping store"))
    assert await run(api.client().scopes()) == ["shipping", "store"]


async def test_never_puts_the_secret_in_an_error(fake: Any) -> None:
    api = fake(lambda call: success({}), lambda: json_response(400, {"error": "invalid_request", "error_description": "grant_type is required."}))
    client = api.client()
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, ReedsError)
    assert "rcs_test_xyz" not in json.dumps({"message": error.message, "raw": error.raw, "repr": repr(error)})


# ------------------------------------------------------------ requests


async def test_sends_the_user_agent_accept_and_default_headers_to_the_base_url(fake: Any) -> None:
    api = fake(lambda call: success({}))
    await run(api.client(base_url="https://api.example.test/", default_headers={"X-Team": "ops"}).shipping.coverage.get())
    call = api.api_calls()[0]
    assert str(call.url) == "https://api.example.test/shipping/v1/coverage"
    assert call.headers["user-agent"] == f"reeds-python/{reeds.__version__} python/{platform.python_version()}"
    assert call.headers["accept"] == "application/json"
    assert call.headers["x-team"] == "ops"
    assert str(api.token_calls()[0].url) == "https://api.example.test/oauth/token"


async def test_an_empty_base_url_means_the_default(fake: Any) -> None:
    api = fake(lambda call: success({}))
    await run(api.client(base_url="").shipping.coverage.get())
    assert api.api_calls()[0].url.host == "api.getreeds.co"


async def test_header_values_that_arent_strings_are_sent_as_strings(fake: Any) -> None:
    api = fake(lambda call: success({}))
    await run(api.client(default_headers={"X-Shard": 3}).shipping.coverage.get(extra_headers={"X-Attempt": 1.5}))
    assert api.api_calls()[0].headers["x-shard"] == "3"
    assert api.api_calls()[0].headers["x-attempt"] == "1.5"


async def test_every_post_gets_an_idempotency_key_and_no_get_or_patch_does(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1")))
    client = api.client()
    await run(client.shipping.deliveries.mark_ready("dlv_1"))
    await run(client.shipping.deliveries.mark_ready("dlv_1"))
    await run(client.shipping.deliveries.get("dlv_1"))
    await run(client.shipping.deliveries.update("dlv_1", reference="R2"))
    first, second, get, patch = api.api_calls()
    assert len(first.headers["idempotency-key"]) == 36
    assert second.headers["idempotency-key"] != first.headers["idempotency-key"]
    assert "idempotency-key" not in get.headers
    assert "idempotency-key" not in patch.headers


async def test_uses_your_idempotency_key(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1"), 201))
    await run(api.client().shipping.deliveries.create(quote_id="qt_1", idempotency_key="order-10045-delivery"))
    assert api.api_calls()[0].headers["idempotency-key"] == "order-10045-delivery"


async def test_returns_the_envelopes_data_as_a_model(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1", status="delivered")))
    found = await run(api.client().shipping.deliveries.get("dlv_1"))
    assert isinstance(found, Delivery)
    assert (found.id, found.status, found.package.description) == ("dlv_1", "delivered", "2 pairs of sneakers")


async def test_keeps_fields_and_values_it_doesnt_know(fake: Any) -> None:
    api = fake(lambda call: success(delivery("dlv_1", status="with_partner", new_field={"a": 1})))
    found = await run(api.client().shipping.deliveries.get("dlv_1"))
    assert found.status == "with_partner"
    assert found.model_extra == {"new_field": {"a": 1}}
    assert found.to_dict()["new_field"] == {"a": 1}


async def test_a_response_missing_a_field_the_spec_requires_still_parses(fake: Any) -> None:
    # Parsing never raises: a POST that charged must not look like it failed.
    api = fake(lambda call: success({"id": "dlv_1", "status": "scheduled", "fee": {"total": 280000}}))
    found = await run(api.client().shipping.deliveries.create(quote_id="qt_1"))
    assert isinstance(found, Delivery)
    assert (found.id, found.status) == ("dlv_1", "scheduled")
    assert found.fee is not None and found.fee.total == 280000
    assert found.to_dict() == {"id": "dlv_1", "status": "scheduled", "fee": {"total": 280000}}


async def test_a_2xx_body_that_isnt_the_envelope_is_an_api_error(fake: Any) -> None:
    api = fake(lambda call: httpx.Response(200, content=b"<html>ok</html>", headers={"x-request-id": "req_x"}))
    client = api.client()
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, APIError)
    assert (error.code, error.request_id) == ("UNEXPECTED_RESPONSE", "req_x")


async def test_gives_up_on_a_timed_out_attempt_after_the_retries(fake: Any) -> None:
    api = fake(lambda call: httpx.ReadTimeout("timed out"))
    client = api.client(timeout=5, max_retries=1)
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, APIConnectionTimeoutError)
    assert error.code == "TIMEOUT"
    assert "5 s" in error.message
    assert len(api.api_calls()) == 2


# ------------------------------------------------------------ retries


async def test_retries_a_429_after_retry_after_with_the_same_idempotency_key(fake: Any) -> None:
    api = fake(sequence(failure(429, "RATE_LIMITED", "Too many requests.", headers={"retry-after": "3"}), success(delivery("dlv_1"), 201)))
    created = await run(api.client().shipping.deliveries.create(quote_id="qt_1"))
    assert created.id == "dlv_1"
    first, second = api.api_calls()
    assert second.headers["idempotency-key"] == first.headers["idempotency-key"]
    assert api.sleeps == [3.0]


async def test_retry_after_can_be_an_http_date(fake: Any) -> None:
    api = fake(lambda call: success({}))
    api.handler = sequence(failure(503, "SERVICE_UNAVAILABLE", headers={"retry-after": formatdate(api.now + 4, usegmt=True)}), success({}))
    await run(api.client().shipping.coverage.get())
    assert api.sleeps == [4.0]


async def test_retries_502_503_and_504_backing_off_half_a_second_then_a_second(fake: Any) -> None:
    api = fake(sequence(failure(502, "INTERNAL_ERROR"), failure(503, "SERVICE_UNAVAILABLE"), success({})))
    await run(api.client().shipping.coverage.get())
    assert len(api.api_calls()) == 3
    assert api.sleeps == [0.5, 1.0]


async def test_retries_a_500_on_a_get_never_on_a_post(fake: Any) -> None:
    get = fake(sequence(failure(500, "INTERNAL_ERROR"), success({})))
    await run(get.client().shipping.coverage.get())
    assert len(get.api_calls()) == 2

    post = fake(sequence(failure(500, "INTERNAL_ERROR"), success(delivery("dlv_1"))))
    client = post.client()
    assert isinstance(await catch(lambda: client.shipping.deliveries.book("dlv_1")), APIError)
    assert len(post.api_calls()) == 1


async def test_retries_409_request_in_progress_but_not_another_409(fake: Any) -> None:
    running = fake(sequence(failure(409, "REQUEST_IN_PROGRESS"), success(delivery("dlv_1"))))
    await run(running.client().shipping.deliveries.book("dlv_1"))
    assert len(running.api_calls()) == 2

    booked = fake(sequence(failure(409, "ACTION_NOT_ALLOWED", "This delivery is already booked.")))
    client = booked.client()
    assert isinstance(await catch(lambda: client.shipping.deliveries.book("dlv_1")), ConflictError)
    assert len(booked.api_calls()) == 1


async def test_retries_a_dropped_connection_then_gives_up_with_a_connection_error(fake: Any) -> None:
    api = fake(lambda call: httpx.ConnectError("connection refused"))
    client = api.client()
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, APIConnectionError) and not isinstance(error, APIConnectionTimeoutError)
    assert error.code == "CONNECTION_FAILED"
    assert len(api.api_calls()) == 3


async def test_stops_after_max_retries_and_raises_the_last_error_with_retry_after(fake: Any) -> None:
    api = fake(lambda call: failure(503, "SERVICE_UNAVAILABLE", "Reeds is busy.", headers={"retry-after": "2"}))
    client = api.client(max_retries=1)
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, ServiceUnavailableError)
    assert error.retry_after == 2
    assert len(api.api_calls()) == 2


async def test_doesnt_wait_out_a_retry_after_longer_than_30_seconds(fake: Any) -> None:
    api = fake(lambda call: failure(429, "RATE_LIMITED", "Slow down.", headers={"retry-after": "120"}))
    client = api.client()
    error = await catch(lambda: client.shipping.quotes.create(pickup={}, dropoff={}, package={}))  # type: ignore[typeddict-item]
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 120
    assert len(api.api_calls()) == 1
    assert api.sleeps == []


async def test_max_retries_per_request_overrides_the_clients(fake: Any) -> None:
    api = fake(lambda call: failure(503, "SERVICE_UNAVAILABLE"))
    client = api.client()
    await catch(lambda: client.shipping.coverage.get(max_retries=0))
    assert len(api.api_calls()) == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [(400, "IDEMPOTENCY_KEY_REQUIRED"), (402, "INSUFFICIENT_BALANCE"), (403, "INSUFFICIENT_SCOPE"), (404, "NOT_FOUND"), (422, "INVALID_REQUEST")],
)
async def test_never_retries_400_402_403_404_or_422(fake: Any, status: int, code: str) -> None:
    api = fake(lambda call: failure(status, code))
    client = api.client()
    await catch(lambda: client.shipping.deliveries.get("dlv_1"))
    assert len(api.api_calls()) == 1


# ------------------------------------------------------------ errors


@pytest.mark.parametrize(
    ("status", "code", "error_class"),
    [
        (400, "IDEMPOTENCY_KEY_REQUIRED", InvalidRequestError),
        (402, "INSUFFICIENT_BALANCE", PaymentRequiredError),
        (403, "INSUFFICIENT_SCOPE", PermissionDeniedError),
        (404, "NOT_FOUND", NotFoundError),
        (409, "QUOTE_ALREADY_USED", ConflictError),
        (422, "INVALID_REQUEST", InvalidRequestError),
    ],
)
async def test_maps_each_status_to_its_class_with_the_code_fields_doc_url_and_request_id(
    fake: Any, status: int, code: str, error_class: type[ReedsError]
) -> None:
    fields = [{"field": "dropoff.lga", "message": "Enter the LGA."}]
    api = fake(lambda call: failure(status, code, "Nope.", {"fields": fields, "delivery_id": "dlv_9"}))
    client = api.client()
    error = await catch(lambda: client.shipping.deliveries.get("dlv_1"))
    assert type(error) is error_class
    assert isinstance(error, ReedsError)
    assert (error.status, error.code, error.message, str(error)) == (status, code, "Nope.", "Nope.")
    assert error.doc_url == f"https://developer.getreeds.co/errors/{code}"
    assert error.request_id == "req_8h2KdP"
    assert error.fields == fields
    assert error.raw is not None and error.raw["delivery_id"] == "dlv_9"


async def test_a_failure_without_a_json_body_still_says_the_status(fake: Any) -> None:
    api = fake(lambda call: httpx.Response(413, content=b"<html>413 Request Entity Too Large</html>"))
    client = api.client()
    error = await catch(lambda: client.shipping.coverage.get())
    assert isinstance(error, APIError)
    assert (error.status, error.code) == (413, "HTTP_413")


# ------------------------------------------------------------ the clients themselves


def test_the_sync_client_closes_its_own_connections_not_yours() -> None:
    mine = httpx.Client()
    with Reeds(client_id="rci_test_x", client_secret="y", http_client=mine) as client:
        assert client.mode == "test"
    assert not mine.is_closed
    mine.close()
    owned = Reeds(client_id="rci_test_x", client_secret="y")
    owned.close()
    assert owned._core._http.is_closed


async def test_the_async_client_closes_its_own_connections_not_yours() -> None:
    mine = httpx.AsyncClient()
    async with AsyncReeds(client_id="rci_test_x", client_secret="y", http_client=mine) as client:
        assert client.mode == "test"
    assert not mine.is_closed
    await mine.aclose()
    owned = AsyncReeds(client_id="rci_test_x", client_secret="y")
    await owned.close()
    assert owned._core._http.is_closed
