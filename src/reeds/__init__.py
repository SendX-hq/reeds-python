"""The official Python library for the Reeds APIs.

    from reeds import Reeds

    reeds = Reeds()  # reads REEDS_CLIENT_ID and REEDS_CLIENT_SECRET
    quote = reeds.shipping.quotes.create(pickup={...}, dropoff={...}, package={...})

See https://github.com/SendX-hq/reeds-python for the guide.
"""

from ._base import Mode
from ._client import AsyncReeds, AsyncWebhooks, Reeds, Webhooks
from ._errors import (
    APIConnectionError,
    APIConnectionTimeoutError,
    APIError,
    AuthenticationError,
    ConflictError,
    ErrorField,
    InvalidRequestError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    ReedsError,
    ServiceUnavailableError,
    WebhookSignatureError,
)
from ._events import ReedsEvent, UnknownEvent
from ._files import FileResponse
from ._models import ReedsModel
from ._pagination import AsyncPage, AsyncPaginator, Page
from ._version import __version__
from ._webhooks import DEFAULT_TOLERANCE, WebhookPayload

webhooks = Webhooks()
"""Webhook verification without a client, for a receiver that only checks events."""

__all__ = [
    "DEFAULT_TOLERANCE",
    "APIConnectionError",
    "APIConnectionTimeoutError",
    "APIError",
    "AsyncPage",
    "AsyncPaginator",
    "AsyncReeds",
    "AsyncWebhooks",
    "AuthenticationError",
    "ConflictError",
    "ErrorField",
    "FileResponse",
    "InvalidRequestError",
    "Mode",
    "NotFoundError",
    "Page",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitError",
    "Reeds",
    "ReedsError",
    "ReedsEvent",
    "ReedsModel",
    "ServiceUnavailableError",
    "UnknownEvent",
    "WebhookPayload",
    "WebhookSignatureError",
    "Webhooks",
    "__version__",
    "webhooks",
]
