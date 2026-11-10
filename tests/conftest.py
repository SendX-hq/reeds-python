from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from .helpers import FakeApi, Flavour


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(params=["sync", "async"])
def flavour(request: pytest.FixtureRequest) -> Flavour:
    """Each test runs against Reeds and against AsyncReeds."""
    flavour: Flavour = request.param
    return flavour


@pytest.fixture
def fake(flavour: Flavour) -> Callable[..., FakeApi]:
    """``fake(handler, token=None)`` -> a FakeApi for this test's flavour."""

    def make(handler: Any, token: Any = None, **kwargs: Any) -> FakeApi:
        return FakeApi(flavour, handler, token, **kwargs)

    return make


@pytest.fixture(autouse=True)
def no_credentials_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests choose their credentials; the developer's own never leak in."""
    monkeypatch.delenv("REEDS_CLIENT_ID", raising=False)
    monkeypatch.delenv("REEDS_CLIENT_SECRET", raising=False)
