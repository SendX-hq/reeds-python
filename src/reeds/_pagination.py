"""Cursor pagination (``limit``, ``starting_after``, ``has_more``).

Sync: ``list()`` returns a Page. Its ``data`` is one page; iterating it walks
every object from that page on, fetching the following pages as needed::

    page = reeds.shipping.deliveries.list(limit=50)
    for delivery in reeds.shipping.deliveries.list():
        ...

Async: ``list()`` returns an AsyncPaginator. Await it for one page, or
``async for`` over it for every object::

    page = await reeds.shipping.deliveries.list(limit=50)
    async for delivery in reeds.shipping.deliveries.list():
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Iterator
from typing import Any, Generic, TypeVar

__all__ = ["AsyncPage", "AsyncPaginator", "Page"]

T = TypeVar("T")


def _cursor(data: list[Any]) -> str | None:
    """The last object's id: where the next page starts."""
    if not data:
        return None
    last = getattr(data[-1], "id", None)
    return last if isinstance(last, str) and last else None


class Page(Generic[T]):
    """One page of a list. Iterating it yields every object from this page on, across pages."""

    data: list[T]
    """This page's objects, newest first."""
    has_more: bool
    """True when another page follows."""

    def __init__(self, data: list[T], has_more: bool, fetch_after: Callable[[str], Page[T]]) -> None:
        self.data = data
        self.has_more = has_more
        self._fetch_after = fetch_after

    def next_page(self) -> Page[T] | None:
        """The next page, or None on the last one."""
        cursor = _cursor(self.data)
        if not self.has_more or cursor is None:
            return None
        return self._fetch_after(cursor)

    def __iter__(self) -> Iterator[T]:
        page: Page[T] | None = self
        while page is not None:
            yield from page.data
            page = page.next_page()

    def __repr__(self) -> str:
        return f"Page(data=[{len(self.data)} objects], has_more={self.has_more})"


class AsyncPage(Generic[T]):
    """One page of a list (async). ``async for`` over it yields every object from this page on."""

    data: list[T]
    """This page's objects, newest first."""
    has_more: bool
    """True when another page follows."""

    def __init__(self, data: list[T], has_more: bool, fetch_after: Callable[[str], Awaitable[AsyncPage[T]]]) -> None:
        self.data = data
        self.has_more = has_more
        self._fetch_after = fetch_after

    async def next_page(self) -> AsyncPage[T] | None:
        """The next page, or None on the last one."""
        cursor = _cursor(self.data)
        if not self.has_more or cursor is None:
            return None
        return await self._fetch_after(cursor)

    async def __aiter__(self) -> AsyncIterator[T]:
        page: AsyncPage[T] | None = self
        while page is not None:
            for item in page.data:
                yield item
            page = await page.next_page()

    def __repr__(self) -> str:
        return f"AsyncPage(data=[{len(self.data)} objects], has_more={self.has_more})"


class AsyncPaginator(Generic[T]):
    """What an async ``list()`` returns: await it for the first page, or ``async for`` over it for every object."""

    def __init__(self, load: Callable[[], Awaitable[AsyncPage[T]]]) -> None:
        self._load = load
        self._page: AsyncPage[T] | None = None

    async def _first(self) -> AsyncPage[T]:
        if self._page is None:
            self._page = await self._load()
        return self._page

    def __await__(self) -> Generator[Any, None, AsyncPage[T]]:
        return self._first().__await__()

    async def __aiter__(self) -> AsyncIterator[T]:
        async for item in await self._first():
            yield item
