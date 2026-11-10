"""What the sync and async clients share: configuration, the token, headers,
the retry rules, envelopes and errors. The HTTP calls themselves live in
_client.py, once per flavour."""

from __future__ import annotations

import json
import os
import platform
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx2

from ._errors import APIConnectionError, APIConnectionTimeoutError, APIError, AuthenticationError, ReedsError
from ._files import FileResponse, filename_of
from ._version import __version__

Mode = Literal["test", "live"]

DEFAULT_BASE_URL = "https://api.getreeds.co"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
REFRESH_MARGIN = 60.0
"""A token is refreshed this many seconds before it expires."""
MAX_RETRY_AFTER_SECONDS = 30.0
"""A Retry-After longer than this isn't waited for: the error goes to the caller, with ``retry_after`` on it."""
TOKEN_PATH = "/oauth/token"


@dataclass(frozen=True)
class Token:
    value: str
    expires_at: float
    scopes: list[str]
    livemode: bool


@dataclass(frozen=True)
class RequestOptions:
    """Per-request settings: an idempotency key, a timeout in seconds, retries, extra headers."""

    idempotency_key: str | None = None
    timeout: float | None = None
    max_retries: int | None = None
    extra_headers: Mapping[str, str] = field(default_factory=dict)


NO_OPTIONS = RequestOptions()


def mode_of(client_id: str | None) -> Mode | None:
    if client_id and client_id.startswith("rci_live_"):
        return "live"
    if client_id and client_id.startswith("rci_test_"):
        return "test"
    return None


def user_agent() -> str:
    return f"reeds-python/{__version__} python/{platform.python_version()}"


def parse_retry_after(value: str | None, now: float) -> float | None:
    """Seconds from a Retry-After header (seconds, or an HTTP date)."""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        return max(0.0, at.timestamp() - now)
    return seconds if seconds >= 0 else None


def read_body(response: httpx2.Response) -> object:
    text = response.text
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def code_of(body: object) -> str | None:
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def encode_query(query: Mapping[str, object] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (query or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            out[key] = ",".join(str(item) for item in value)
        else:
            out[key] = str(value)
    return out


def encode_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class BaseCore:
    """Configuration and everything about a request that isn't sending it."""

    base_url: str
    mode: Mode | None
    """"test" or "live", from the client id; None when there is none (webhook verification only)."""

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        base_url: str | None,
        timeout: float | None,
        max_retries: int | None,
        default_headers: Mapping[str, str] | None,
    ) -> None:
        self._client_id = client_id if client_id is not None else (os.environ.get("REEDS_CLIENT_ID") or None)
        self._client_secret = client_secret if client_secret is not None else (os.environ.get("REEDS_CLIENT_SECRET") or None)
        # An empty string (an unset environment variable passed through) means the default too.
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.mode = mode_of(self._client_id)
        self.timeout = DEFAULT_TIMEOUT if timeout is None else float(timeout)
        self.max_retries = DEFAULT_MAX_RETRIES if max_retries is None else int(max_retries)
        self.default_headers = dict(default_headers or {})
        self._token: Token | None = None
        # Test hooks.
        self._now = time.time
        self._random = random.random

    # ------------------------------------------------------------ the token

    def _fresh(self, token: Token | None) -> bool:
        return token is not None and token.expires_at - REFRESH_MARGIN > self._now()

    def _check_credentials(self) -> tuple[str, str]:
        if not self._client_id or not self._client_secret:
            raise AuthenticationError(
                "Pass client_id and client_secret, or set REEDS_CLIENT_ID and REEDS_CLIENT_SECRET. Find them in Dashboard → Developers.",
                code="MISSING_CREDENTIALS",
            )
        return self._client_id, self._client_secret

    def _token_form(self) -> dict[str, str]:
        client_id, client_secret = self._check_credentials()
        return {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}

    def _token_from(self, response: httpx2.Response) -> Token:
        body = read_body(response)
        access_token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(body, dict) or not isinstance(access_token, str) or not access_token:
            raise APIError(
                "The token endpoint answered without an access token.",
                code="UNEXPECTED_RESPONSE",
                status=response.status_code,
                request_id=response.headers.get("x-request-id"),
            )
        expires_in = body.get("expires_in")
        scope = body.get("scope")
        self._token = Token(
            value=access_token,
            expires_at=self._now() + (float(expires_in) if isinstance(expires_in, (int, float)) else 3600.0),
            scopes=scope.split() if isinstance(scope, str) else [],
            livemode=bool(body.get("livemode")),
        )
        return self._token

    def _forget(self, token: Token) -> None:
        """Drops the cached token after a 401, unless another call already replaced it."""
        if self._token is not None and self._token.value == token.value:
            self._token = None

    # ------------------------------------------------------------ requests

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _headers(
        self,
        *,
        accept: str,
        token: Token | None,
        idempotency_key: str | None,
        content_type: str | None,
        options: RequestOptions,
    ) -> dict[str, str]:
        headers = {"Accept": accept, **self.default_headers, "User-Agent": user_agent()}
        if token is not None:
            headers["Authorization"] = f"Bearer {token.value}"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        if content_type is not None:
            headers["Content-Type"] = content_type
        headers.update(options.extra_headers)
        return {key: str(value) for key, value in headers.items()}

    @staticmethod
    def _retryable(method: str, status: int, code: str | None) -> bool:
        """Retried: no response, 429, 502, 503, 504, a 500 on a GET, and 409 REQUEST_IN_PROGRESS (the same key still running)."""
        if status in (429, 502, 503, 504):
            return True
        if status == 500:
            return method == "GET"
        return status == 409 and code == "REQUEST_IN_PROGRESS"

    def _backoff(self, attempt: int) -> float:
        """About 0.5 s, then 1 s, 2 s ..., at most 8 s, with jitter."""
        return float(min(8.0, 0.5 * 2**attempt) * (1 - 0.25 * self._random()))

    @staticmethod
    def _connection_error(error: httpx2.HTTPError, timeout: float) -> ReedsError:
        if isinstance(error, httpx2.TimeoutException):
            return APIConnectionTimeoutError(f"No answer from Reeds within {timeout:g} s.", code="TIMEOUT")
        return APIConnectionError(f"Couldn't reach Reeds: {error}", code="CONNECTION_FAILED")

    # ------------------------------------------------------------ responses

    @staticmethod
    def _unexpected(response: httpx2.Response) -> APIError:
        return APIError(
            f"Reeds answered {response.status_code} with a body this version of the library doesn't recognise.",
            code="UNEXPECTED_RESPONSE",
            status=response.status_code,
            request_id=response.headers.get("x-request-id"),
        )

    def _data(self, response: httpx2.Response) -> Any:
        body = read_body(response)
        if not isinstance(body, dict) or body.get("status") != "success" or "data" not in body:
            raise self._unexpected(response)
        return body["data"]

    def _list(self, response: httpx2.Response) -> tuple[list[Any], bool]:
        body = read_body(response)
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise self._unexpected(response)
        return body["data"], bool(body.get("has_more"))

    @staticmethod
    def _file(response: httpx2.Response) -> FileResponse:
        return FileResponse(
            data=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
            filename=filename_of(response.headers.get("content-disposition")),
        )
