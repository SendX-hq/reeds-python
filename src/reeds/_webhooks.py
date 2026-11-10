"""Webhook signatures, the same for every Reeds API::

    Reeds-Signature: t=<unix seconds>,v1=<hex>[,v1=<hex>]

Each v1 is the hex HMAC-SHA256 of ``t + "." + raw body``, keyed with the
endpoint's signing secret (``whsec_test_...`` or ``whsec_live_...``). During a
secret rotation the header carries two v1 values for 24 hours; any match is
enough. Then ``t`` must be within 5 minutes of now: every attempt, retries
included, is signed afresh when it is sent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Sequence
from typing import NoReturn, TypeAlias

from ._errors import WebhookSignatureError

__all__ = ["DEFAULT_TOLERANCE", "WebhookPayload", "construct_event_data", "verify_signature"]

DEFAULT_TOLERANCE = 300
"""Seconds a signed event stays valid either side of now."""

WebhookPayload: TypeAlias = str | bytes | bytearray | memoryview
"""The raw request body: the exact bytes Reeds sent (or them decoded as UTF-8). Never parsed JSON."""

_HEX = re.compile(r"[0-9a-fA-F]+")
_DIGITS = re.compile(r"[0-9]+")


def _fail(code: str, message: str) -> NoReturn:
    raise WebhookSignatureError(message, code=code)


def _bytes_of(payload: object) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)
    _fail(
        "RAW_BODY_REQUIRED",
        "Pass the raw request body (str or bytes), not parsed JSON: a re-serialised body never matches the signature. See the README for your framework.",
    )


def _parse_header(header: str | None) -> tuple[int, list[str]]:
    if not isinstance(header, str) or header.strip() == "":
        _fail("NO_SIGNATURE_HEADER", "The request has no Reeds-Signature header.")
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key == "t" and _DIGITS.fullmatch(value):
            timestamp = int(value)
        if key == "v1" and value:
            signatures.append(value)
    if timestamp is None:
        _fail("INVALID_SIGNATURE_HEADER", "The Reeds-Signature header has no valid t= timestamp.")
    if not signatures:
        _fail("NO_SIGNATURE", "The Reeds-Signature header has no v1= signature.")
    return timestamp, signatures


def _secrets_of(secret: str | Sequence[str]) -> list[str]:
    secrets = [secret] if isinstance(secret, str) else list(secret)
    if not secrets or any(not isinstance(value, str) or value == "" for value in secrets):
        _fail("NO_SECRET", "Pass your webhook endpoint's signing secret (whsec_...), from Dashboard → Developers.")
    if any(value.startswith("rcs_") for value in secrets):
        _fail(
            "WRONG_SECRET_TYPE",
            "That's a client secret. Webhooks are signed with the endpoint's signing secret (whsec_...), from Dashboard → Developers.",
        )
    return secrets


def _matches(expected: bytes, given: str) -> bool:
    if not _HEX.fullmatch(given) or len(given) != len(expected) * 2:
        return False
    return hmac.compare_digest(expected, bytes.fromhex(given))


def verify_signature(
    payload: WebhookPayload,
    header: str | None,
    secret: str | Sequence[str],
    *,
    tolerance: int = DEFAULT_TOLERANCE,
    now: int | None = None,
) -> None:
    """Raises WebhookSignatureError unless ``header`` signs ``payload`` with ``secret``, within ``tolerance`` seconds."""
    secrets = _secrets_of(secret)
    body = _bytes_of(payload)
    timestamp, signatures = _parse_header(header)
    signed_payload = f"{timestamp}.".encode() + body
    signed = any(_matches(hmac.new(value.encode("utf-8"), signed_payload, hashlib.sha256).digest(), given) for value in secrets for given in signatures)
    if not signed:
        _fail("SIGNATURE_MISMATCH", "No signature in the Reeds-Signature header matches this body and secret.")
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance:
        _fail(
            "TIMESTAMP_OUTSIDE_TOLERANCE",
            f"The event was signed {abs(current - timestamp)} s from now; the limit is {tolerance} s.",
        )


def construct_event_data(
    payload: WebhookPayload,
    header: str | None,
    secret: str | Sequence[str],
    *,
    tolerance: int = DEFAULT_TOLERANCE,
    now: int | None = None,
) -> object:
    """Verifies the signature, then returns the decoded JSON."""
    verify_signature(payload, header, secret, tolerance=tolerance, now=now)
    try:
        return json.loads(_bytes_of(payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        _fail("INVALID_PAYLOAD", "The signed body isn't JSON.")
