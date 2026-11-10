"""The Reeds API clients. One client, one set of credentials, every Reeds API::

    reeds = Reeds()  # reads REEDS_CLIENT_ID and REEDS_CLIENT_SECRET
    quote = reeds.shipping.quotes.create(pickup={...}, dropoff={...}, package={...})

``AsyncReeds`` is the same with ``await``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import TracebackType

import httpx
from typing_extensions import Self, Unpack

from ._base import Mode
from ._core import AsyncCore, SyncCore
from ._events import ReedsEvent, parse_event
from ._webhooks import DEFAULT_TOLERANCE, WebhookPayload, construct_event_data, verify_signature
from .shipping._async_resources import AsyncShipping
from .shipping._generated import TestWebhookRequestParam, TestWebhookResult
from .shipping._resources import Shipping, options, path

__all__ = ["AsyncReeds", "AsyncWebhooks", "Reeds", "Webhooks"]


class _Checks:
    """Signature checks: no credentials or network needed."""

    def verify_signature(
        self,
        payload: WebhookPayload,
        header: str | None,
        secret: str | Sequence[str],
        *,
        tolerance: int = DEFAULT_TOLERANCE,
        now: int | None = None,
    ) -> None:
        """Raises WebhookSignatureError unless ``header`` signs ``payload`` (the raw body) with ``secret``, within 5 minutes.

        ``secret`` can be a list: both secrets while you rotate one.
        """
        verify_signature(payload, header, secret, tolerance=tolerance, now=now)

    def construct_event(
        self,
        payload: WebhookPayload,
        header: str | None,
        secret: str | Sequence[str],
        *,
        tolerance: int = DEFAULT_TOLERANCE,
        now: int | None = None,
    ) -> ReedsEvent:
        """Verifies the signature, then returns the event. Pass the raw body (str or bytes), not parsed JSON."""
        return parse_event(construct_event_data(payload, header, secret, tolerance=tolerance, now=now))


class Webhooks(_Checks):
    """Webhooks are account-wide: one endpoint per account and mode gets every Reeds API's events, signed the same way.

    ``Webhooks()`` alone verifies events; ``Reeds().webhooks`` can also send test events.
    """

    def __init__(self, core: SyncCore | None = None) -> None:
        self._core = core

    def send_test(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[TestWebhookRequestParam],
    ) -> TestWebhookResult:
        """Sends a signed test event to the endpoint saved for this mode (Dashboard → Developers)."""
        if self._core is None:
            raise RuntimeError("send_test needs a client: use Reeds(...).webhooks.send_test().")
        result: TestWebhookResult = self._core.post(
            path("webhooks", "test"), TestWebhookResult, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result


class AsyncWebhooks(_Checks):
    """Webhooks on the async client. Checking a signature needs no network, so it isn't async."""

    def __init__(self, core: AsyncCore | None = None) -> None:
        self._core = core

    async def send_test(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[TestWebhookRequestParam],
    ) -> TestWebhookResult:
        """Sends a signed test event to the endpoint saved for this mode (Dashboard → Developers)."""
        if self._core is None:
            raise RuntimeError("send_test needs a client: use AsyncReeds(...).webhooks.send_test().")
        result: TestWebhookResult = await self._core.post(
            path("webhooks", "test"), TestWebhookResult, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result


class Reeds:
    """The Reeds API client.

    :param client_id: ``rci_test_...`` or ``rci_live_...``. Defaults to the REEDS_CLIENT_ID environment variable.
    :param client_secret: ``rcs_test_...`` or ``rcs_live_...``. Defaults to REEDS_CLIENT_SECRET.
    :param base_url: Defaults to https://api.getreeds.co.
    :param timeout: Seconds to wait for a response before giving up on an attempt. Default 60.
    :param max_retries: How many times a failed request is retried when it is safe to. Default 2.
    :param default_headers: Headers sent with every request.
    :param http_client: An httpx.Client to send with (proxies, custom TLS). The client doesn't close it.
    """

    shipping: Shipping
    """The Shipping API: quotes, deliveries, the wallet, invoices and the sandbox."""
    webhooks: Webhooks
    """Webhook signature checks and test events, for every API."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._core = SyncCore(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self.shipping = Shipping(self._core)
        self.webhooks = Webhooks(self._core)

    @property
    def mode(self) -> Mode | None:
        """``"test"`` or ``"live"``, from the client id; None without one."""
        return self._core.mode

    def scopes(self) -> list[str]:
        """The scopes your credentials carry: one per Reeds API your account may use (for example ``["shipping"]``)."""
        return self._core.scopes()

    def close(self) -> None:
        """Closes the connections (not an http_client you passed in)."""
        self._core.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


class AsyncReeds:
    """The Reeds API client, async. The same options as Reeds; ``http_client`` is an httpx.AsyncClient."""

    shipping: AsyncShipping
    """The Shipping API: quotes, deliveries, the wallet, invoices and the sandbox."""
    webhooks: AsyncWebhooks
    """Webhook signature checks and test events, for every API."""

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._core = AsyncCore(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self.shipping = AsyncShipping(self._core)
        self.webhooks = AsyncWebhooks(self._core)

    @property
    def mode(self) -> Mode | None:
        """``"test"`` or ``"live"``, from the client id; None without one."""
        return self._core.mode

    async def scopes(self) -> list[str]:
        """The scopes your credentials carry: one per Reeds API your account may use (for example ``["shipping"]``)."""
        return await self._core.scopes()

    async def close(self) -> None:
        """Closes the connections (not an http_client you passed in)."""
        await self._core.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.close()
