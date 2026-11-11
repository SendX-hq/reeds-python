"""The Shipping API on the sync client: ``reeds.shipping``."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import quote

from typing_extensions import Unpack

from .._base import BaseCore, RequestOptions
from .._core import SyncCore
from .._errors import PermissionDeniedError
from .._files import FileResponse
from .._pagination import Page
from ._generated import (
    AdvanceRequestParam,
    AutocompleteAddressesParams,
    BookFromQuoteParam,
    CancelRequestParam,
    Coverage,
    Delivery,
    DeliveryUpdateParam,
    FundWalletRequestParam,
    FundWalletResponse,
    GetAddressDetailsParams,
    Invoice,
    ListDeliveriesParams,
    ListInvoicesParams,
    ListWalletTransactionsParams,
    Place,
    PlaceSuggestionsResult,
    Quote,
    QuoteRequestParam,
    QuoteUnavailable,
    ReverseGeocodeAddressParams,
    Wallet,
    WalletTransaction,
)

__all__ = ["Addresses", "Coverages", "Deliveries", "Invoices", "Quotes", "Sandbox", "Shipping", "WalletResource"]

SHIPPING_PATH = "/shipping/v1"
"""The Shipping API's base path."""


def path(*parts: str) -> str:
    return SHIPPING_PATH + "".join("/" + quote(part, safe="") for part in parts)


def options(
    idempotency_key: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> RequestOptions:
    return RequestOptions(idempotency_key=idempotency_key, timeout=timeout, max_retries=max_retries, extra_headers=extra_headers or {})


def refuse_live(core: BaseCore) -> None:
    """Sandbox calls are refused here, before any request, with live credentials."""
    if core.mode == "live":
        raise PermissionDeniedError("Sandbox calls work with test credentials (rci_test_...) only.", code="TEST_MODE_ONLY")


class Coverages:
    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def get(self, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Coverage:
        """The states, zones and inter-state routes Reeds serves."""
        result: Coverage = self._core.get(path("coverage"), Coverage, options=options(None, timeout, max_retries, extra_headers))
        return result


class Addresses:
    """Address search: suggestions as a customer types, a place's full address, the address at a map pin.

    Free, within what Reeds sets for the account: past it, ``PermissionDeniedError`` with the code
    ``ADDRESS_SEARCH_LIMIT_REACHED``, or ``ADDRESS_SEARCH_DISABLED`` when Reeds has switched it off.
    """

    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def autocomplete(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[AutocompleteAddressesParams],
    ) -> PlaceSuggestionsResult:
        """Places in Nigeria for what the customer has typed, best first. Use one ``session_token`` per address being typed."""
        result: PlaceSuggestionsResult = self._core.get(
            path("addresses", "autocomplete"), PlaceSuggestionsResult, query=params, options=options(None, timeout, max_retries, extra_headers)
        )
        return result

    def details(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[GetAddressDetailsParams],
    ) -> Place:
        """The full address of a place. Send the search's ``session_token`` so this ends that search instead of counting as another."""
        result: Place = self._core.get(path("addresses", "details"), Place, query=params, options=options(None, timeout, max_retries, extra_headers))
        return result

    def reverse(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[ReverseGeocodeAddressParams],
    ) -> Place:
        """The address nearest to a map pin in Nigeria. Each call is one search."""
        result: Place = self._core.get(path("addresses", "reverse"), Place, query=params, options=options(None, timeout, max_retries, extra_headers))
        return result


class Quotes:
    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def create(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[QuoteRequestParam],
    ) -> Quote | QuoteUnavailable:
        """Prices a delivery. A route Reeds doesn't serve is not an error: the answer has ``available=False`` and a ``reason``."""
        result: Quote | QuoteUnavailable = self._core.post(
            path("quotes"), Quote | QuoteUnavailable, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result


class Deliveries:
    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def create(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[BookFromQuoteParam],
    ) -> Delivery:
        """Books the delivery a quote priced, and charges it. Sends an Idempotency-Key (yours, or a new one)."""
        result: Delivery = self._core.post(path("deliveries"), Delivery, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers))
        return result

    def list(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[ListDeliveriesParams],
    ) -> Page[Delivery]:
        """Deliveries, newest first: one page, which iterates across every page."""
        return self._core.list(path("deliveries"), Delivery, query=params, options=options(None, timeout, max_retries, extra_headers))

    def get(self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Delivery:
        result: Delivery = self._core.get(path("deliveries", id), Delivery, options=options(None, timeout, max_retries, extra_headers))
        return result

    def update(
        self,
        id: str,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[DeliveryUpdateParam],
    ) -> Delivery:
        """Changes the reference, instructions or metadata."""
        result: Delivery = self._core.patch(path("deliveries", id), Delivery, json=params, options=options(None, timeout, max_retries, extra_headers))
        return result

    def book(
        self,
        id: str,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Delivery:
        """Books and charges a priced delivery made in the dashboard (one waiting on BOOK, FUND_WALLET or PAY_INVOICE)."""
        result: Delivery = self._core.post(path("deliveries", id, "book"), Delivery, options=options(idempotency_key, timeout, max_retries, extra_headers))
        return result

    def mark_ready(
        self,
        id: str,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Delivery:
        """The item is packed: the pickup is scheduled from now. Only a paid delivery can be marked ready (409 otherwise)."""
        result: Delivery = self._core.post(path("deliveries", id, "ready"), Delivery, options=options(idempotency_key, timeout, max_retries, extra_headers))
        return result

    def cancel(
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
        result: Delivery = self._core.post(
            path("deliveries", id, "cancel"), Delivery, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    def label(self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> FileResponse:
        """The shipping label, as a PDF."""
        return self._core.file(path("deliveries", id, "label"), options=options(None, timeout, max_retries, extra_headers))


class WalletResource:
    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def get(self, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Wallet:
        result: Wallet = self._core.get(path("wallet"), Wallet, options=options(None, timeout, max_retries, extra_headers))
        return result

    def fund(
        self,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[FundWalletRequestParam],
    ) -> FundWalletResponse:
        """Live mode: starts a Paystack payment and returns the URL to send the payer to. In Test mode use ``sandbox.fund_wallet``."""
        result: FundWalletResponse = self._core.post(
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
    ) -> Page[WalletTransaction]:
        """The wallet's ledger, newest first: one page, which iterates across every page."""
        return self._core.list(path("wallet", "transactions"), WalletTransaction, query=params, options=options(None, timeout, max_retries, extra_headers))


class Invoices:
    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def list(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Unpack[ListInvoicesParams],
    ) -> Page[Invoice]:
        return self._core.list(path("invoices"), Invoice, query=params, options=options(None, timeout, max_retries, extra_headers))

    def get(self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> Invoice:
        result: Invoice = self._core.get(path("invoices", id), Invoice, options=options(None, timeout, max_retries, extra_headers))
        return result

    def pdf(self, id: str, *, timeout: float | None = None, max_retries: int | None = None, extra_headers: Mapping[str, str] | None = None) -> FileResponse:
        """The invoice as a PDF."""
        return self._core.file(path("invoices", id, "pdf"), options=options(None, timeout, max_retries, extra_headers))


class Sandbox:
    """Test mode only. Refused here, before any request, with live credentials."""

    def __init__(self, core: SyncCore) -> None:
        self._core = core

    def fund_wallet(
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
        result: Wallet = self._core.post(
            path("sandbox", "wallet", "fund"), Wallet, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result

    def advance_delivery(
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
        result: Delivery = self._core.post(
            path("sandbox", "deliveries", id, "advance"), Delivery, json=params, options=options(idempotency_key, timeout, max_retries, extra_headers)
        )
        return result


class Shipping:
    """The Shipping API: coverage, address search, quotes, deliveries, the wallet, invoices and the sandbox."""

    coverage: Coverages
    addresses: Addresses
    quotes: Quotes
    deliveries: Deliveries
    wallet: WalletResource
    invoices: Invoices
    sandbox: Sandbox

    def __init__(self, core: SyncCore) -> None:
        self.coverage = Coverages(core)
        self.addresses = Addresses(core)
        self.quotes = Quotes(core)
        self.deliveries = Deliveries(core)
        self.wallet = WalletResource(core)
        self.invoices = Invoices(core)
        self.sandbox = Sandbox(core)
