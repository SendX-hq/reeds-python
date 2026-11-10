"""Webhook signatures: the shared vectors every Reeds library must agree on, and construct_event."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from reeds import AsyncReeds, Reeds, UnknownEvent, Webhooks, WebhookSignatureError, webhooks
from reeds.shipping import DeliveryBookedEvent

VECTORS: dict[str, Any] = json.loads((Path(__file__).parent / "fixtures" / "webhook-vectors.json").read_text(encoding="utf-8"))


def outcome(run: Any) -> str:
    try:
        run()
    except WebhookSignatureError as error:
        return error.code
    return "valid"


@pytest.mark.parametrize("vector", VECTORS["cases"], ids=[case["name"] for case in VECTORS["cases"]])
def test_the_shared_vectors_made_by_the_apis_own_signer(vector: dict[str, Any]) -> None:
    expected = "valid" if vector["valid"] else vector["error"]
    tolerance, now = VECTORS["tolerance"], vector["now"]
    payload: str = vector["payload"]
    # The body as text, as bytes (a raw-body read gives bytes), and as a memoryview.
    for body in (payload, payload.encode(), memoryview(payload.encode())):
        assert outcome(lambda body=body: webhooks.verify_signature(body, vector["header"], vector["secrets"], tolerance=tolerance, now=now)) == expected


def test_all_21_vectors_are_there() -> None:
    assert len(VECTORS["cases"]) == 21


VALID = next(case for case in VECTORS["cases"] if case["name"] == "valid")
FUTURE = next(case for case in VECTORS["cases"] if case["name"].startswith("an event type"))


@pytest.mark.parametrize(
    "checker", [webhooks, Webhooks(), Reeds().webhooks, AsyncReeds().webhooks], ids=["module", "standalone", "sync client", "async client"]
)
def test_construct_event_returns_the_typed_event_once_the_signature_checks_out(checker: Any) -> None:
    event = checker.construct_event(VALID["payload"], VALID["header"], VALID["secrets"], now=VALID["now"])
    assert isinstance(event, DeliveryBookedEvent)
    assert event.type == "delivery.booked"
    assert event.data.delivery.id == "dlv_9Kd3Qx7M"
    assert event.data.delivery.fee is not None and event.data.delivery.fee.total == 280000


def test_an_event_type_it_doesnt_know_yet_is_an_unknown_event_not_an_error() -> None:
    event = webhooks.construct_event(FUTURE["payload"], FUTURE["header"], FUTURE["secrets"], now=FUTURE["now"])
    assert isinstance(event, UnknownEvent)
    assert event.type == "order.paid"


def test_refuses_a_parsed_body_and_says_to_pass_the_raw_one() -> None:
    with pytest.raises(WebhookSignatureError) as error:
        webhooks.construct_event(json.loads(VALID["payload"]), VALID["header"], VALID["secrets"], now=VALID["now"])
    assert error.value.code == "RAW_BODY_REQUIRED"


def test_refuses_a_client_secret_which_never_signs_webhooks() -> None:
    assert outcome(lambda: webhooks.verify_signature(VALID["payload"], VALID["header"], "rcs_test_xyz", now=VALID["now"])) == "WRONG_SECRET_TYPE"


def test_refuses_no_secret() -> None:
    assert outcome(lambda: webhooks.verify_signature(VALID["payload"], VALID["header"], "", now=VALID["now"])) == "NO_SECRET"
    assert outcome(lambda: webhooks.verify_signature(VALID["payload"], VALID["header"], [], now=VALID["now"])) == "NO_SECRET"


def test_checks_the_time_against_the_clock_by_default() -> None:
    # The vectors were signed on 2026-11-09; with the real clock the valid one may be too old.
    expected = "TIMESTAMP_OUTSIDE_TOLERANCE" if abs(int(time.time()) - VALID["now"]) > 300 else "valid"
    assert outcome(lambda: webhooks.verify_signature(VALID["payload"], VALID["header"], VALID["secrets"])) == expected


def test_send_test_needs_a_client() -> None:
    with pytest.raises(RuntimeError, match="needs a client"):
        Webhooks().send_test()
