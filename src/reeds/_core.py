"""The HTTP calls, once for each flavour: SyncCore (httpx2.Client) and
AsyncCore (httpx2.AsyncClient). Both follow the same rules, from _base.py:

- one token per client, fetched on first use, refreshed a minute before it
  expires, one refresh at a time; a 401 TOKEN_EXPIRED or UNAUTHENTICATED gets
  one fresh token and one more try;
- every POST carries an Idempotency-Key (yours, or a new UUID), and retries
  reuse it;
- retried: no response, 429, 502, 503, 504, a 500 on a GET, 409
  REQUEST_IN_PROGRESS; Retry-After is honoured up to 30 s, otherwise about
  0.5 s, 1 s, 2 s ... with jitter, at most 8 s.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlencode

import httpx2

from ._base import (
    MAX_RETRY_AFTER_SECONDS,
    NO_OPTIONS,
    TOKEN_PATH,
    BaseCore,
    RequestOptions,
    Token,
    code_of,
    encode_json,
    encode_query,
    parse_retry_after,
    read_body,
)
from ._errors import error_from_response
from ._files import FileResponse
from ._pagination import AsyncPage, AsyncPaginator, Page
from ._parse import parse

__all__ = ["AsyncCore", "SyncCore"]

_NO_BODY: Any = object()


class _Prepared:
    """What stays the same across the attempts of one request."""

    def __init__(self, core: BaseCore, method: str, auth: bool, json: Any, form: Mapping[str, str] | None, options: RequestOptions) -> None:
        self.idempotency_key: str | None = None
        if auth:
            # Every POST to an API carries a key, so a retry can never create or charge twice.
            self.idempotency_key = options.idempotency_key if options.idempotency_key is not None else (str(uuid.uuid4()) if method == "POST" else None)
        self.max_retries = core.max_retries if options.max_retries is None else options.max_retries
        self.timeout = core.timeout if options.timeout is None else float(options.timeout)
        self.content: bytes | None = None
        self.content_type: str | None = None
        if form is not None:
            self.content = urlencode(dict(form)).encode("ascii")
            self.content_type = "application/x-www-form-urlencoded"
        elif json is not _NO_BODY:
            self.content = encode_json(json)
            self.content_type = "application/json"


class SyncCore(BaseCore):
    def __init__(self, *, http_client: httpx2.Client | None = None, **config: Any) -> None:
        super().__init__(**config)
        self._http = http_client if http_client is not None else httpx2.Client(timeout=self.timeout)
        self._owns_http = http_client is None
        self._lock = threading.Lock()
        self._sleep: Callable[[float], None] = time.sleep

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    # ------------------------------------------------------------ the token

    def scopes(self) -> list[str]:
        return list(self._get_token().scopes)

    def _get_token(self) -> Token:
        token = self._token
        if token is not None and self._fresh(token):
            return token
        # One refresh at a time: concurrent calls wait for it, then use its token.
        with self._lock:
            token = self._token
            if token is not None and self._fresh(token):
                return token
            response = self.send("POST", TOKEN_PATH, form=self._token_form(), auth=False)
            return self._token_from(response)

    # ------------------------------------------------------------ calls the modules make

    def get(self, path: str, cast_to: Any, *, query: Mapping[str, object] | None = None, options: RequestOptions = NO_OPTIONS) -> Any:
        return parse(cast_to, self._data(self.send("GET", path, query=query, options=options)))

    def post(self, path: str, cast_to: Any, *, json: Any = _NO_BODY, options: RequestOptions = NO_OPTIONS) -> Any:
        return parse(cast_to, self._data(self.send("POST", path, json=json, options=options)))

    def patch(self, path: str, cast_to: Any, *, json: Any, options: RequestOptions = NO_OPTIONS) -> Any:
        return parse(cast_to, self._data(self.send("PATCH", path, json=json, options=options)))

    def list(self, path: str, item: Any, *, query: Mapping[str, object], options: RequestOptions = NO_OPTIONS) -> Page[Any]:
        def load(params: dict[str, object]) -> Page[Any]:
            data, has_more = self._list(self.send("GET", path, query=params, options=options))
            return Page([parse(item, entry) for entry in data], has_more, lambda after: load({**params, "starting_after": after}))

        return load(dict(query))

    def file(self, path: str, *, options: RequestOptions = NO_OPTIONS) -> FileResponse:
        return self._file(self.send("GET", path, accept="application/pdf", options=options))

    # ------------------------------------------------------------ one request, with retries

    def send(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        json: Any = _NO_BODY,
        form: Mapping[str, str] | None = None,
        accept: str = "application/json",
        auth: bool = True,
        options: RequestOptions = NO_OPTIONS,
    ) -> httpx2.Response:
        prepared = _Prepared(self, method, auth, json, form, options)
        url, params = self._url(path), encode_query(query)
        refreshed = False
        attempt = 0
        while True:
            token = self._get_token() if auth else None
            headers = self._headers(accept=accept, token=token, idempotency_key=prepared.idempotency_key, content_type=prepared.content_type, options=options)
            try:
                response = self._http.request(method, url, params=params, content=prepared.content, headers=headers, timeout=prepared.timeout)
            except httpx2.RequestError as error:
                if attempt < prepared.max_retries:
                    self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise self._connection_error(error, prepared.timeout) from error
            if response.is_success:
                return response

            body = read_body(response)
            code = code_of(body)
            # The token expired or was revoked: one fresh token, one more try (not counted as a retry).
            if token is not None and response.status_code == 401 and not refreshed and code in ("TOKEN_EXPIRED", "UNAUTHENTICATED"):
                self._forget(token)
                refreshed = True
                continue
            retry_after = parse_retry_after(response.headers.get("retry-after"), self._now())
            if (
                attempt < prepared.max_retries
                and self._retryable(method, response.status_code, code)
                and (retry_after is None or retry_after <= MAX_RETRY_AFTER_SECONDS)
            ):
                self._sleep(retry_after if retry_after is not None else self._backoff(attempt))
                attempt += 1
                continue
            raise error_from_response(response.status_code, body, response.headers, retry_after)


class AsyncCore(BaseCore):
    def __init__(self, *, http_client: httpx2.AsyncClient | None = None, **config: Any) -> None:
        super().__init__(**config)
        self._http = http_client if http_client is not None else httpx2.AsyncClient(timeout=self.timeout)
        self._owns_http = http_client is None
        self._lock: asyncio.Lock | None = None
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # ------------------------------------------------------------ the token

    async def scopes(self) -> list[str]:
        return list((await self._get_token()).scopes)

    async def _get_token(self) -> Token:
        token = self._token
        if token is not None and self._fresh(token):
            return token
        # One refresh at a time: concurrent calls wait for it, then use its token.
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            token = self._token
            if token is not None and self._fresh(token):
                return token
            response = await self.send("POST", TOKEN_PATH, form=self._token_form(), auth=False)
            return self._token_from(response)

    # ------------------------------------------------------------ calls the modules make

    async def get(self, path: str, cast_to: Any, *, query: Mapping[str, object] | None = None, options: RequestOptions = NO_OPTIONS) -> Any:
        return parse(cast_to, self._data(await self.send("GET", path, query=query, options=options)))

    async def post(self, path: str, cast_to: Any, *, json: Any = _NO_BODY, options: RequestOptions = NO_OPTIONS) -> Any:
        return parse(cast_to, self._data(await self.send("POST", path, json=json, options=options)))

    async def patch(self, path: str, cast_to: Any, *, json: Any, options: RequestOptions = NO_OPTIONS) -> Any:
        return parse(cast_to, self._data(await self.send("PATCH", path, json=json, options=options)))

    def list(self, path: str, item: Any, *, query: Mapping[str, object], options: RequestOptions = NO_OPTIONS) -> AsyncPaginator[Any]:
        async def load(params: dict[str, object]) -> AsyncPage[Any]:
            data, has_more = self._list(await self.send("GET", path, query=params, options=options))
            return AsyncPage([parse(item, entry) for entry in data], has_more, lambda after: load({**params, "starting_after": after}))

        first = dict(query)
        return AsyncPaginator(lambda: load(first))

    async def file(self, path: str, *, options: RequestOptions = NO_OPTIONS) -> FileResponse:
        return self._file(await self.send("GET", path, accept="application/pdf", options=options))

    # ------------------------------------------------------------ one request, with retries

    async def send(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        json: Any = _NO_BODY,
        form: Mapping[str, str] | None = None,
        accept: str = "application/json",
        auth: bool = True,
        options: RequestOptions = NO_OPTIONS,
    ) -> httpx2.Response:
        prepared = _Prepared(self, method, auth, json, form, options)
        url, params = self._url(path), encode_query(query)
        refreshed = False
        attempt = 0
        while True:
            token = await self._get_token() if auth else None
            headers = self._headers(accept=accept, token=token, idempotency_key=prepared.idempotency_key, content_type=prepared.content_type, options=options)
            try:
                response = await self._http.request(method, url, params=params, content=prepared.content, headers=headers, timeout=prepared.timeout)
            except httpx2.RequestError as error:
                if attempt < prepared.max_retries:
                    await self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise self._connection_error(error, prepared.timeout) from error
            if response.is_success:
                return response

            body = read_body(response)
            code = code_of(body)
            # The token expired or was revoked: one fresh token, one more try (not counted as a retry).
            if token is not None and response.status_code == 401 and not refreshed and code in ("TOKEN_EXPIRED", "UNAUTHENTICATED"):
                self._forget(token)
                refreshed = True
                continue
            retry_after = parse_retry_after(response.headers.get("retry-after"), self._now())
            if (
                attempt < prepared.max_retries
                and self._retryable(method, response.status_code, code)
                and (retry_after is None or retry_after <= MAX_RETRY_AFTER_SECONDS)
            ):
                await self._sleep(retry_after if retry_after is not None else self._backoff(attempt))
                attempt += 1
                continue
            raise error_from_response(response.status_code, body, response.headers, retry_after)
