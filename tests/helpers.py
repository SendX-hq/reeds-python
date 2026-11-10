"""A fake Reeds API behind a real httpx2 transport, for both clients.

Every test runs twice, against Reeds and AsyncReeds (the ``api`` fixture in
conftest.py). Tests stay flavour-blind with ``run`` (await it if it's
awaitable), ``catch`` (the error a call raises) and ``collect`` (every item of
a sync or async iteration).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl

import httpx2

from reeds import AsyncReeds, Reeds

Flavour = Literal["sync", "async"]


@dataclass
class Call:
    url: httpx2.URL
    method: str
    headers: dict[str, str]
    body: str | None

    @property
    def form(self) -> dict[str, str]:
        return dict(parse_qsl(self.body or ""))


Answer = httpx2.Response | Exception
Handler = Callable[[Call], Answer]


def json_response(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx2.Response:
    content = b"" if body is None else json.dumps(body).encode()
    return httpx2.Response(status, content=content, headers={"content-type": "application/json", "x-request-id": "req_8h2KdP", **(headers or {})})


def success(data: Any, status: int = 200) -> httpx2.Response:
    return json_response(status, {"status": "success", "data": data})


def failure(
    status: int, code: str, message: str = "Something's wrong.", extra: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> httpx2.Response:
    error = {"code": code, "message": message, "doc_url": f"https://developer.getreeds.co/errors/{code}", **(extra or {})}
    return json_response(status, {"status": "failed", "error": error}, headers)


def token_response(access_token: str = "tok_1", **extra: Any) -> httpx2.Response:
    return json_response(200, {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600, "scope": "shipping", "livemode": False, **extra})


def delivery(id: str, **extra: Any) -> dict[str, Any]:
    """A delivery as the API sends it (every required field)."""
    return {
        "id": id,
        "livemode": False,
        "channel": "direct",
        "status": "scheduled",
        "reference": "ORDER-10045",
        "required_actions": [],
        "cancellable": True,
        "package": {"description": "2 pairs of sneakers", "quantity": 1},
        "ready": True,
        "auto_book": False,
        "created_at": "2026-11-09T10:20:00+01:00",
        "updated_at": "2026-11-09T10:20:00+01:00",
        **extra,
    }


def sequence(*answers: Answer) -> Handler:
    """Answers in turn; the last one repeats."""
    state = {"i": 0}

    def handler(_call: Call) -> Answer:
        answer = answers[min(state["i"], len(answers) - 1)]
        state["i"] += 1
        return answer

    return handler


class FakeApi:
    """Every request is recorded; the token endpoint answers a fresh token unless ``token`` says otherwise."""

    def __init__(self, flavour: Flavour, handler: Handler, token: Callable[[], Answer] | None = None, token_delay: float = 0.0) -> None:
        self.flavour = flavour
        self.handler = handler
        self.token = token or (lambda: token_response())
        self.token_delay = token_delay
        self.calls: list[Call] = []
        self.sleeps: list[float] = []
        self.now = 1_793_016_302.0

    def _record(self, request: httpx2.Request) -> tuple[Call, bool]:
        call = Call(url=request.url, method=request.method, headers={k.lower(): v for k, v in request.headers.items()}, body=request.content.decode() or None)
        self.calls.append(call)
        return call, request.url.path == "/oauth/token"

    def _answer(self, call: Call, is_token: bool) -> httpx2.Response:
        answer = self.token() if is_token else self.handler(call)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def _sync_handle(self, request: httpx2.Request) -> httpx2.Response:
        call, is_token = self._record(request)
        if is_token and self.token_delay:
            time.sleep(self.token_delay)
        return self._answer(call, is_token)

    async def _async_handle(self, request: httpx2.Request) -> httpx2.Response:
        call, is_token = self._record(request)
        if is_token and self.token_delay:
            await asyncio.sleep(self.token_delay)
        return self._answer(call, is_token)

    def client(self, **options: Any) -> Any:
        """A Reeds or AsyncReeds on this fake, with test credentials unless overridden. Sleeps are recorded, not slept."""
        settings = {"client_id": "rci_test_abc", "client_secret": "rcs_test_xyz", **options}
        client: Reeds | AsyncReeds
        if self.flavour == "sync":
            client = Reeds(http_client=httpx2.Client(transport=httpx2.MockTransport(self._sync_handle)), **settings)

            def sleep(seconds: float) -> None:
                self.sleeps.append(seconds)

            client._core._sleep = sleep
        else:
            client = AsyncReeds(http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self._async_handle)), **settings)

            async def asleep(seconds: float) -> None:
                self.sleeps.append(seconds)

            client._core._sleep = asleep
        client._core._now = lambda: self.now
        client._core._random = lambda: 0.0
        return client

    def api_calls(self) -> list[Call]:
        """The calls to the API itself, not the token endpoint."""
        return [call for call in self.calls if call.url.path != "/oauth/token"]

    def token_calls(self) -> list[Call]:
        return [call for call in self.calls if call.url.path == "/oauth/token"]


async def run(value: Any) -> Any:
    """A call's result, for either client: awaits it when it is awaitable."""
    return await value if inspect.isawaitable(value) else value


async def catch(call: Callable[[], Any]) -> Any:
    """The exception a call raises (sync or async)."""
    try:
        await run(call())
    except Exception as error:
        return error
    raise AssertionError("expected the call to raise")


async def collect(iterable: Any) -> list[Any]:
    """Every item of a sync or async iteration."""
    if hasattr(iterable, "__aiter__"):
        return [item async for item in iterable]
    return list(iterable)
