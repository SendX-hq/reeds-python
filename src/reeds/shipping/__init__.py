"""The Shipping API's types: ``from reeds.shipping import Delivery, Quote``.

Objects the API returns are Pydantic models with the API's own field names;
request parameters are TypedDicts. Both are generated from the Shipping API's
OpenAPI spec (spec/shipping-v1.yaml) into _generated.py, and everything there
is exported here.
"""

from typing import TypeAlias

from . import _generated
from ._async_resources import AsyncShipping
from ._generated import *  # noqa: F403
from ._generated import (
    SHIPPING_EVENTS,
    AdvanceRequestParam,
    BookFromQuoteParam,
    CancelRequestParam,
    DeliveryUpdateParam,
    FundWalletRequestParam,
    FundWalletResponse,
    ListDeliveriesParams,
    ListInvoicesParams,
    ListWalletTransactionsParams,
    QuoteRequestParam,
    TestWebhookRequestParam,
)
from ._resources import SHIPPING_PATH, Shipping

# The names reeds-node and reeds-php use, for the same shapes.
QuoteCreateParams: TypeAlias = QuoteRequestParam
DeliveryCreateParams: TypeAlias = BookFromQuoteParam
DeliveryListParams: TypeAlias = ListDeliveriesParams
DeliveryUpdateParams: TypeAlias = DeliveryUpdateParam
DeliveryCancelParams: TypeAlias = CancelRequestParam
WalletFundParams: TypeAlias = FundWalletRequestParam
WalletFundResult: TypeAlias = FundWalletResponse
WalletTransactionListParams: TypeAlias = ListWalletTransactionsParams
InvoiceListParams: TypeAlias = ListInvoicesParams
SandboxFundParams: TypeAlias = FundWalletRequestParam
SandboxAdvanceParams: TypeAlias = AdvanceRequestParam
TestWebhookParams: TypeAlias = TestWebhookRequestParam

SHIPPING_EVENT_TYPES: tuple[str, ...] = tuple(SHIPPING_EVENTS)
"""Every webhook event type the Shipping API sends."""

__all__ = [
    "SHIPPING_EVENT_TYPES",
    "SHIPPING_PATH",
    "AsyncShipping",
    "DeliveryCancelParams",
    "DeliveryCreateParams",
    "DeliveryListParams",
    "DeliveryUpdateParams",
    "InvoiceListParams",
    "QuoteCreateParams",
    "SandboxAdvanceParams",
    "SandboxFundParams",
    "Shipping",
    "TestWebhookParams",
    "WalletFundParams",
    "WalletFundResult",
    "WalletTransactionListParams",
]
__all__ += _generated.__all__
