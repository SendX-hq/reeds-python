"""The README's webhook handlers, run in real FastAPI, Flask and Django apps:
a correctly signed event is accepted, a tampered one is refused with 400.

The frameworks aren't dependencies of the library: install the `frameworks`
dependency group to run these (CI does); without them they skip.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import pytest

from .helpers import delivery

SECRET = "whsec_test_frameworksA1b2C3d4"
BODY = json.dumps(
    {"id": "evt_4fQ7Hd2X", "type": "delivery.booked", "created_at": "2026-11-09T10:20:00+01:00", "livemode": False, "data": {"delivery": delivery("dlv_9")}}
)
TAMPERED = BODY.replace("ORDER-10045", "ORDER-99999")


def signature(body: str) -> str:
    timestamp = int(time.time())
    digest = hmac.new(SECRET.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REEDS_WEBHOOK_SECRET", SECRET)


def test_fastapi() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from .frameworks.fastapi_app import app

    client = TestClient(app)
    headers = {"Reeds-Signature": signature(BODY), "Content-Type": "application/json"}
    assert client.post("/webhooks/reeds", content=BODY, headers=headers).status_code == 200
    refused = client.post("/webhooks/reeds", content=TAMPERED, headers=headers)
    assert refused.status_code == 400
    assert "No signature" in refused.text


def test_flask() -> None:
    pytest.importorskip("flask")
    from .frameworks.flask_app import app

    client = app.test_client()
    headers = {"Reeds-Signature": signature(BODY)}
    assert client.post("/webhooks/reeds", data=BODY, headers=headers, content_type="application/json").status_code == 200
    refused = client.post("/webhooks/reeds", data=TAMPERED, headers=headers, content_type="application/json")
    assert refused.status_code == 400
    assert "No signature" in refused.get_data(as_text=True)


def django_settings() -> Any:
    pytest.importorskip("django")
    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            ROOT_URLCONF="tests.frameworks.django_app",
            ALLOWED_HOSTS=["testserver"],
            SECRET_KEY="reeds-tests",
            # A real project's CSRF protection: the README's @csrf_exempt is what lets Reeds in.
            MIDDLEWARE=["django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware"],
            INSTALLED_APPS=[],
        )
        django.setup()
    return settings


def test_django() -> None:
    django_settings()
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    headers = {"Reeds-Signature": signature(BODY)}
    assert client.post("/webhooks/reeds", data=BODY, content_type="application/json", headers=headers).status_code == 200
    refused = client.post("/webhooks/reeds", data=TAMPERED, content_type="application/json", headers=headers)
    assert refused.status_code == 400
    assert b"No signature" in refused.content
    assert client.get("/webhooks/reeds").status_code == 405
