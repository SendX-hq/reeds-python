"""The Shipping API on the async client: ``reeds.shipping`` of ``AsyncReeds``."""

from __future__ import annotations

from collections.abc import Mapping

from typing_extensions import Unpack

from .._core import AsyncCore
from .._files import FileResponse
from .._pagination import AsyncPaginator
from ._generated import (
    AdvanceRequestParam,
    BookFromQuoteParam,
    CancelRequestParam,
    Coverage,
    Delivery,
    DeliveryUpdateParam,
    FundWalletRequestParam,
    FundWalletResponse,
    Invoice,
    ListDeliveriesParams,
    ListInvoicesParams,
    ListWalletTransactionsParams,
    Quote,
    QuoteRequestParam,
    QuoteUnavailable,
    Wallet,
    WalletTransaction,
)
from ._resources import options, path, refuse_live

__all__ = ["AsyncCoverages", "AsyncDeliveries", "AsyncInvoices", "AsyncQuotes", "AsyncSandbox", "AsyncShipping", "AsyncWalletResource"]


class AsyncCoverages:
    def __init__(self, core: AsyncCore) -> None:
        self._core = core

    async def get(self, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Coverage:
        """The states, zones and inter-state routes Reeds serves."""
        result: Coverage = await self._core.get(path("coverage"), Coverage, options=options(None, timeout, max_retries, extra_headers))
        return result


class AsyncQuotes:
    def __init__(self, core: AsyncCore) -> None:
        self._core = core

    async def create(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[QuoteRequestParam],
    ) -> Quote | QuoteUnavailable:
        """Prices a delivery. A route Reeds doesn't serve is not an error: the answer has ``available=False`` and a ``reason``."""
        result: Quote | QuoteUnavailable = await self._core.post(
            path("quotes"), Quote | QuoteUnavailable, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result


class AsyncDeliveries:
    def __init__(self, core: AsyncCore) -> None:
        self._core = core

    async def create(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[BookFromQuoteParam],
    ) -> Delivery:
        """Books the delivery a quote priced, and charges it. Sends an Idempotency-Key (yours, or a new one)."""
        result: Delivery = await self._core.post(
            path("deliveries"), Delivery, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    def list(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[ListDeliveriesParams],
    ) -> AsyncPaginator[Delivery]:
        """Deliveries, newest first: await it for one page, or ``async for`` over it for every object."""
        return self._core.list(path("deliveries"), Delivery, query=params, options=options(None, timeout, max_retries, extra_headers))

    async def get(self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Delivery:
        result: Delivery = await self._core.get(path("deliveries", id), Delivery, options=options(None, timeout, max_retries, extra_headers))
        return result

    async def update(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[DeliveryUpdateParam],
    ) -> Delivery:
        """Changes the reference, instructions or metadata."""
        result: Delivery = await self._core.patch(path("deliveries", id), Delivery, json=params, options=options(None, timeout, max_retries, extra_headers))
        return result

    async def book(
        self,
        id: str,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Delivery:
        """Books and charges a priced delivery made in the dashboard (one waiting on BOOK, FUND_WALLET or PAY_INVOICE)."""
        result: Delivery = await self._core.post(
            path("deliveries", id, "book"), Delivery, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    async def mark_ready(
        self,
        id: str,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Delivery:
        """The item is packed: the pickup is scheduled from now. Only a paid delivery can be marked ready (409 otherwise)."""
        result: Delivery = await self._core.post(
            path("deliveries", id, "ready"), Delivery, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    async def cancel(
        self,
        id: str,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[CancelRequestParam],
    ) -> Delivery:
        """Cancels and refunds in full, until the rider sets off."""
        result: Delivery = await self._core.post(
            path("deliveries", id, "cancel"), Delivery, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    async def label(
        self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None
    ) -> FileResponse:
        """The shipping label, as a PDF."""
        return await self._core.file(path("deliveries", id, "label"), options=options(None, timeout, max_retries, extra_headers))


class AsyncWalletResource:
    def __init__(self, core: AsyncCore) -> None:
        self._core = core

    async def get(self, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Wallet:
        result: Wallet = await self._core.get(path("wallet"), Wallet, options=options(None, timeout, max_retries, extra_headers))
        return result

    async def fund(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[FundWalletRequestParam],
    ) -> FundWalletResponse:
        """Live mode: starts a Paystack payment and returns the URL to send the payer to. In Test mode use ``sandbox.fund_wallet``."""
        result: FundWalletResponse = await self._core.post(
            path("wallet", "fund"), FundWalletResponse, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    def list_transactions(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[ListWalletTransactionsParams],
    ) -> AsyncPaginator[WalletTransaction]:
        """The wallet's ledger, newest first: await it for one page, or ``async for`` over it for every object."""
        return self._core.list(path("wallet", "transactions"), WalletTransaction, query=params, options=options(None, timeout, max_retries, extra_headers))


class AsyncInvoices:
    def __init__(self, core: AsyncCore) -> None:
        self._core = core

    def list(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[ListInvoicesParams],
    ) -> AsyncPaginator[Invoice]:
        return self._core.list(path("invoices"), Invoice, query=params, options=options(None, timeout, max_retries, extra_headers))

    async def get(self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Invoice:
        result: Invoice = await self._core.get(path("invoices", id), Invoice, options=options(None, timeout, max_retries, extra_headers))
        return result

    async def pdf(
        self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None
    ) -> FileResponse:
        """The invoice as a PDF."""
        return await self._core.file(path("invoices", id, "pdf"), options=options(None, timeout, max_retries, extra_headers))


class AsyncSandbox:
    """Test mode only. Refused here, before any request, with live credentials."""

    def __init__(self, core: AsyncCore) -> None:
        self._core = core

    async def fund_wallet(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[FundWalletRequestParam],
    ) -> Wallet:
        """Tops up the test wallet at once, and books deliveries made in the dashboard that waited for funds."""
        refuse_live(self._core)
        result: Wallet = await self._core.post(
            path("sandbox", "wallet", "fund"), Wallet, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    async def advance_delivery(
        self,
        id: str,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[AdvanceRequestParam],
    ) -> Delivery:
        """Moves a test delivery to the next status, or to the one you name."""
        refuse_live(self._core)
        result: Delivery = await self._core.post(
            path("sandbox", "deliveries", id, "advance"), Delivery, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result


class AsyncShipping:
    """The Shipping API: quotes, deliveries, the wallet, invoices and the sandbox."""

    coverage: AsyncCoverages
    quotes: AsyncQuotes
    deliveries: AsyncDeliveries
    wallet: AsyncWalletResource
    invoices: AsyncInvoices
    sandbox: AsyncSandbox

    def __init__(self, core: AsyncCore) -> None:
        self.coverage = AsyncCoverages(core)
        self.quotes = AsyncQuotes(core)
        self.deliveries = AsyncDeliveries(core)
        self.wallet = AsyncWalletResource(core)
        self.invoices = AsyncInvoices(core)
        self.sandbox = AsyncSandbox(core)
