"""Every failure is a ReedsError.

Branch on the class or on ``code``, never on the message, which Reeds can
reword. The subclass says what kind of failure it is, so
``isinstance(error, RateLimitError)`` and ``error.code == "RATE_LIMITED"`` agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from typing_extensions import TypedDict

__all__ = [
    "APIConnectionError",
    "APIConnectionTimeoutError",
    "APIError",
    "AuthenticationError",
    "ConflictError",
    "ErrorField",
    "InvalidRequestError",
    "NotFoundError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitError",
    "ReedsError",
    "ServiceUnavailableError",
    "WebhookSignatureError",
]


class ErrorField(TypedDict):
    """One invalid field of a ``422 INVALID_REQUEST``."""

    field: str
    message: str


class ReedsError(Exception):
    """The base of every error the library raises."""

    status: int | None
    """The HTTP status, or None when no response came (or the library refused before sending)."""
    code: str
    """The API's stable code, such as ``INSUFFICIENT_BALANCE``, or the OAuth error (``invalid_client``)."""
    message: str
    fields: list[ErrorField]
    """Each invalid field, on ``422 INVALID_REQUEST``."""
    doc_url: str | None
    """The code's page on the developer hub."""
    request_id: str | None
    """The ``X-Request-Id`` of the call. Quote it to Reeds support."""
    retry_after: float | None
    """The seconds Reeds asked you to wait (``429`` and ``503``)."""
    raw: dict[str, Any] | None
    """The API's ``error`` object as sent, including fields only some codes carry (``delivery_id``)."""
    headers: Mapping[str, str] | None

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status: int | None = None,
        fields: list[ErrorField] | None = None,
        doc_url: str | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
        raw: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.fields = fields if fields is not None else []
        self.doc_url = doc_url
        self.request_id = request_id
        self.retry_after = retry_after
        self.raw = raw
        self.headers = headers

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, status={self.status!r}, message={self.message!r}, request_id={self.request_id!r})"


class AuthenticationError(ReedsError):
    """401, or the token endpoint refusing the credentials."""


class PermissionDeniedError(ReedsError):
    """403: the credentials can't do this (a missing scope, an IP not allowed, a sandbox call with live credentials)."""


class NotFoundError(ReedsError):
    """404."""


class ConflictError(ReedsError):
    """409: the object's state doesn't allow it (already booked, cancelled, a quote already used)."""


class InvalidRequestError(ReedsError):
    """400 or 422: the request itself is wrong. ``fields`` lists each invalid field."""


class PaymentRequiredError(ReedsError):
    """402: the wallet or credit doesn't cover it (``INSUFFICIENT_BALANCE``, ``CREDIT_LIMIT_REACHED``)."""


class RateLimitError(ReedsError):
    """429. ``retry_after`` is the seconds Reeds asked you to wait."""


class ServiceUnavailableError(ReedsError):
    """503: Reeds is shedding load and did nothing. ``retry_after`` is the seconds to wait."""


class APIError(ReedsError):
    """Any other failure status (5xx), or a response the library doesn't recognise."""


class APIConnectionError(ReedsError):
    """No response: the network failed."""


class APIConnectionTimeoutError(APIConnectionError):
    """No response within the timeout."""


class WebhookSignatureError(ReedsError):
    """A webhook whose signature or timestamp doesn't check out. Answer 400 and don't act on it."""


_BY_STATUS: dict[int, type[ReedsError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: InvalidRequestError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}


def error_class_for(status: int) -> type[ReedsError]:
    return _BY_STATUS.get(status, APIError)


def error_from_response(status: int, body: object, headers: Mapping[str, str], retry_after: float | None) -> ReedsError:
    """The error for a failed response, from its body: the failure envelope, an OAuth error, or anything else."""
    request_id = headers.get("x-request-id")
    error_class = error_class_for(status)
    error = body.get("error") if isinstance(body, dict) else None
    # The API's failure envelope: {"status": "failed", "error": {"code", "message", "doc_url", "fields"?}}.
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        doc_url = error.get("doc_url")
        fields = error.get("fields")
        return error_class(
            message if isinstance(message, str) else f"Reeds answered {status}.",
            code=code if isinstance(code, str) else f"HTTP_{status}",
            status=status,
            fields=fields if isinstance(fields, list) else [],
            doc_url=doc_url if isinstance(doc_url, str) else None,
            request_id=request_id,
            retry_after=retry_after,
            raw=error,
            headers=headers,
        )
    # The token endpoint's OAuth errors: {"error": "invalid_client", "error_description": "..."}.
    if isinstance(body, dict) and isinstance(error, str):
        description = body.get("error_description")
        return error_class(
            description if isinstance(description, str) else error,
            code=error,
            status=status,
            request_id=request_id,
            retry_after=retry_after,
            raw=body,
            headers=headers,
        )
    # Not JSON (a proxy's HTML page, say).
    return error_class(
        f"Reeds answered {status} without an error body.",
        code=f"HTTP_{status}",
        status=status,
        request_id=request_id,
        retry_after=retry_after,
        headers=headers,
    )
