"""The library against its specs: every operation has a method on both clients,
every event type has a model, and the generated types match the spec. When the
sync-spec workflow brings in a new operation, this fails until the method exists."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

import reeds
from reeds import AsyncReeds, Reeds
from reeds.shipping import SHIPPING_EVENT_TYPES, SHIPPING_EVENTS

ROOT = Path(__file__).resolve().parent.parent
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def spec(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((ROOT / "spec" / name).read_text(encoding="utf-8"))
    return loaded


def operation_ids(document: dict[str, Any]) -> list[str]:
    return [op["operationId"] for item in document["paths"].values() for method, op in item.items() if method in HTTP_METHODS]


def shipping_methods(client: Any) -> dict[str, Any]:
    """operationId -> the method that calls it. The token endpoint is the core's."""
    s = client.shipping
    return {
        "createAccessToken": "core",
        "getCoverage": s.coverage.get,
        "autocompleteAddresses": s.addresses.autocomplete,
        "getAddressDetails": s.addresses.details,
        "reverseGeocodeAddress": s.addresses.reverse,
        "createQuote": s.quotes.create,
        "createDelivery": s.deliveries.create,
        "listDeliveries": s.deliveries.list,
        "getDelivery": s.deliveries.get,
        "updateDelivery": s.deliveries.update,
        "bookDelivery": s.deliveries.book,
        "markDeliveryReady": s.deliveries.mark_ready,
        "cancelDelivery": s.deliveries.cancel,
        "getDeliveryLabel": s.deliveries.label,
        "getWallet": s.wallet.get,
        "fundWallet": s.wallet.fund,
        "listWalletTransactions": s.wallet.list_transactions,
        "listInvoices": s.invoices.list,
        "getInvoice": s.invoices.get,
        "getInvoicePdf": s.invoices.pdf,
        "sendTestWebhook": client.webhooks.send_test,
        "sandboxFundWallet": s.sandbox.fund_wallet,
        "sandboxAdvanceDelivery": s.sandbox.advance_delivery,
    }


def test_every_shipping_operation_has_a_method_on_both_clients_and_every_method_an_operation() -> None:
    expected = sorted(operation_ids(spec("shipping-v1.yaml")))
    for client in (Reeds(client_id="rci_test_x", client_secret="x"), AsyncReeds(client_id="rci_test_x", client_secret="x")):
        methods = shipping_methods(client)
        assert sorted(methods) == expected
        for operation_id, method in methods.items():
            assert method == "core" or callable(method), operation_id


def test_every_webhook_event_type_has_a_model() -> None:
    hooks = spec("shipping-v1.yaml")["webhooks"]
    assert sorted(SHIPPING_EVENT_TYPES) == sorted(hooks)
    for event_type, model in SHIPPING_EVENTS.items():
        assert model.model_fields["type"].annotation is not str, event_type


def test_the_generated_types_match_the_spec() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate.py"), "--check"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_the_version_is_the_packages() -> None:
    assert reeds.__version__ == importlib.metadata.version("reeds-sdk")
