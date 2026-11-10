"""Generates src/reeds/<api>/_generated.py from spec/<api>-v<n>.yaml.

    python scripts/generate.py

The specs in spec/ are copies of sendx-api's openapi/*.yaml, taken by the
sync-spec workflow; never edit them or the generated files by hand.

What it writes, for each API:

- Response models (Pydantic, ``extra="allow"``) for every object an operation
  or a webhook returns, named after the spec's schemas. Inline objects get
  ``<Parent><Field>`` names (``WalletCredit``), array items ``...Item``.
- Request parameters as TypedDicts named ``<Schema>Param``, and each list
  operation's query as ``<OperationId>Params``.
- Enums as ``Literal[...] | str`` when they have two or more values: Reeds adds
  values inside a version, so an unknown one must still type-check and parse.
  Single-value enums stay exact: they are discriminants (an event's ``type``).
- Each webhook event as a model, the ``ShippingEvent`` union and
  ``SHIPPING_EVENTS`` (type -> model).

The output is deterministic: the same spec always gives the same file, and CI
fails when the committed file differs from a fresh run.
"""

from __future__ import annotations

import json
import keyword
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Api:
    name: str
    spec: str
    out: str
    #: Fields Reeds always sends in an event's data, though the spec doesn't mark them required yet
    #: (the same list as reeds-node's src/apis/shipping/events.ts).
    always_present: dict[str, list[str]] = field(default_factory=dict)
    #: Query parameters typed wider than the spec says: (operationId, name) -> Python type.
    query_overrides: dict[tuple[str, str], str] = field(default_factory=dict)


APIS = [
    Api(
        name="shipping",
        spec="spec/shipping-v1.yaml",
        out="src/reeds/shipping/_generated.py",
        always_present={
            "DeliveryCreatedEvent": ["delivery"],
            "DeliveryRequiresActionEvent": ["delivery", "required_action"],
            "DeliveryBookedEvent": ["delivery"],
            "DeliveryStatusChangedEvent": ["delivery", "previous_status"],
            "DeliveryScheduleChangedEvent": ["delivery", "previous_schedule"],
            "DeliveryExpiringEvent": ["delivery", "expires_at"],
            "DeliveryCancelledEvent": ["delivery", "cancellation"],
            "WalletFundedEvent": ["amount", "currency", "balance", "transaction"],
            "WalletLowBalanceEvent": ["balance", "low_balance_threshold", "currency"],
            "InvoiceIssuedEvent": ["invoice"],
            "InvoicePaidEvent": ["invoice"],
            "InvoiceOverdueEvent": ["invoice"],
        },
        # Up to 50 delivery ids, as a list or comma-separated.
        query_overrides={("listDeliveries", "ids"): "str | Sequence[str]"},
    )
]

#: Schemas the core handles itself: the token, the envelopes, the error shape, the event envelope.
CORE_SCHEMAS = {"TokenRequest", "TokenResponse", "OAuthError", "SuccessEnvelope", "ListEnvelope", "Error", "WebhookEventBase"}
HTTP_METHODS = ("get", "post", "put", "patch", "delete")
#: Names a model field can't take: Python keywords and pydantic.BaseModel's own attributes.
RESERVED = set(keyword.kwlist) | {"model_config", "model_fields", "model_extra", "dict", "json", "copy", "schema", "construct", "validate"}


def pascal(text: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[^0-9A-Za-z]+", text) if part)


def q(value: Any) -> str:
    """A Python literal, strings in double quotes."""
    return json.dumps(value) if isinstance(value, str) else repr(value)


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def doc(text: str | None, indent: str) -> list[str]:
    """A docstring from a spec description, one paragraph per line of the (folded) YAML text."""
    if not text:
        return []
    paragraphs = [" ".join(line.split()).replace("\\", "\\\\").replace('"', '\\"') for line in text.strip().split("\n") if line.strip()]
    if len(paragraphs) == 1:
        return [f'{indent}"""{paragraphs[0]}"""']
    lines = [f'{indent}"""{paragraphs[0]}']
    for paragraph in paragraphs[1:]:
        lines += ["", f"{indent}{paragraph}"]
    return lines + [f'{indent}"""']


class Generator:
    def __init__(self, api: Api) -> None:
        self.api = api
        self.spec: dict[str, Any] = yaml.safe_load((ROOT / api.spec).read_text(encoding="utf-8"))
        self.schemas: dict[str, Any] = self.spec["components"]["schemas"]
        self.parameters: dict[str, Any] = self.spec["components"].get("parameters", {})
        self.taken: set[str] = set(self.schemas)
        self.aliases: dict[str, str] = {}  # name -> definition
        self.models: dict[str, list[str]] = {}  # name -> lines, in dependency order
        self.params: dict[str, list[str]] = {}  # TypedDicts, in dependency order
        self.events: list[tuple[str, str]] = []  # (type, model)

    # ------------------------------------------------------------ shapes

    def resolve(self, schema: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in schema:
            schema = self.schemas[ref_name(schema["$ref"])]
        return schema

    def merged(self, schema: dict[str, Any]) -> dict[str, Any]:
        """An allOf flattened into one object schema (properties and required merged)."""
        if "allOf" not in schema:
            return schema
        out: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        if schema.get("description"):
            out["description"] = schema["description"]
        for part in schema["allOf"]:
            part = self.merged(self.resolve(part))
            out["properties"].update(part.get("properties", {}))
            out["required"] += [name for name in part.get("required", []) if name not in out["required"]]
            out.setdefault("description", part.get("description"))
        return out

    @staticmethod
    def nullable_parts(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """(the schema without null, whether null is allowed)."""
        kinds = schema.get("type")
        if isinstance(kinds, list) and "null" in kinds:
            rest = [kind for kind in kinds if kind != "null"]
            return {**schema, "type": rest[0] if len(rest) == 1 else rest}, True
        for key in ("oneOf", "anyOf"):
            options = schema.get(key)
            if isinstance(options, list) and any(option.get("type") == "null" for option in options):
                rest = [option for option in options if option.get("type") != "null"]
                return (rest[0] if len(rest) == 1 else {key: rest}), True
        return schema, False

    @staticmethod
    def is_enum(schema: dict[str, Any]) -> bool:
        return isinstance(schema.get("enum"), list)

    @staticmethod
    def literal(values: list[Any]) -> str:
        literals = ", ".join(q(value) for value in values)
        if all(isinstance(value, str) for value in values) and len(values) >= 2:
            return f"Literal[{literals}] | str"
        return f"Literal[{literals}]"

    def is_alias_object(self, schema: dict[str, Any]) -> bool:
        return schema.get("type") == "object" and not schema.get("properties") and "allOf" not in schema

    def fresh_name(self, base: str) -> str:
        name = base if base not in self.taken else base + "Detail"
        self.taken.add(name)
        return name

    # ------------------------------------------------------------ types

    def py_type(self, schema: dict[str, Any], owner: str, prop: str, side: str) -> str:
        """The Python type of a property. side is "model" (responses) or "param" (requests)."""
        schema, nullable = self.nullable_parts(schema)
        text = self.base_type(schema, owner, prop, side)
        return f"{text} | None" if nullable and not text.endswith("| None") else text

    def base_type(self, schema: dict[str, Any], owner: str, prop: str, side: str) -> str:
        if "$ref" in schema:
            return self.named(ref_name(schema["$ref"]), side)
        for key in ("oneOf", "anyOf"):
            if key in schema:
                return " | ".join(self.py_type(option, owner, prop, side) for option in schema[key])
        if "allOf" in schema:
            return self.object_type(self.merged(schema), owner, prop, side)
        if self.is_enum(schema):
            return self.literal(schema["enum"])
        kind = schema.get("type")
        if kind == "string":
            return "str"
        if kind == "integer":
            return "int"
        if kind == "number":
            return "float"
        if kind == "boolean":
            return "bool"
        if kind == "array":
            item = self.py_type(schema.get("items", {}), owner, prop + "Item", side)
            return f"list[{item}]"
        if kind == "object":
            return self.object_type(schema, owner, prop, side)
        return "Any"

    def object_type(self, schema: dict[str, Any], owner: str, prop: str, side: str) -> str:
        if schema.get("properties"):
            name = self.fresh_name(owner + pascal(prop) + ("Param" if side == "param" else ""))
            self.emit(name, schema, side)
            return name
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            return f"dict[str, {self.py_type(extra, owner, prop, side)}]"
        return "dict[str, Any]"

    def named(self, name: str, side: str) -> str:
        """A $ref: an enum alias, a dict alias, or a model / TypedDict (emitted on first use)."""
        schema = self.schemas[name]
        if self.is_enum(schema):
            if name not in self.aliases:
                self.aliases[name] = self.literal(schema["enum"])
            return name
        if self.is_alias_object(schema):
            if name not in self.aliases:
                self.aliases[name] = self.object_type(schema, name, "", side)
            return name
        target = name + "Param" if side == "param" else name
        if target not in self.models and target not in self.params:
            self.emit(target, self.merged(schema), side, description=schema.get("description"))
        return target

    # ------------------------------------------------------------ classes

    def emit(self, name: str, schema: dict[str, Any], side: str, description: str | None = None, required_extra: list[str] | None = None) -> None:
        store = self.models if side == "model" else self.params
        store[name] = []  # placeholder, so a reference back to it doesn't recurse
        schema = self.merged(schema)
        required = set(schema.get("required", [])) | set(required_extra or [])
        body: list[str] = []
        for prop, prop_schema in schema.get("properties", {}).items():
            if side == "model":
                body += self.model_field(name, prop, prop_schema, prop in required)
            else:
                body += self.param_field(name, prop, prop_schema, prop in required)
        del store[name]
        if side == "model":
            lines = [f"class {name}(ReedsModel):"] + doc(description or schema.get("description"), "    ")
        else:
            lines = [f"class {name}(TypedDict):"] + doc(description or schema.get("description"), "    ")
        store[name] = lines + (body or ["    pass"])

    def model_field(self, owner: str, prop: str, schema: dict[str, Any], required: bool) -> list[str]:
        text = self.py_type(schema, owner, pascal(prop), "model")
        attr = prop + "_" if prop in RESERVED or not prop.isidentifier() else prop
        if required:
            line = f"    {attr}: {text}" if attr == prop else f"    {attr}: {text} = Field(alias={q(prop)})"
        else:
            optional = text if text.endswith("| None") else f"{text} | None"
            line = f"    {attr}: {optional} = None" if attr == prop else f"    {attr}: {optional} = Field(default=None, alias={q(prop)})"
        return [line] + doc(schema.get("description") or self.resolve(schema).get("description"), "    ")

    def param_field(self, owner: str, prop: str, schema: dict[str, Any], required: bool) -> list[str]:
        if not prop.isidentifier() or keyword.iskeyword(prop):
            raise SystemExit(f"{owner}.{prop}: a request field that isn't a Python identifier needs the functional TypedDict form")
        text = self.py_type(schema, owner.removesuffix("Param"), pascal(prop), "param")
        line = f"    {prop}: {text}" if required else f"    {prop}: NotRequired[{text}]"
        return [line] + doc(schema.get("description") or self.resolve(schema).get("description"), "    ")

    # ------------------------------------------------------------ the spec walk

    def operations(self) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
        out = []
        for path, item in self.spec.get("paths", {}).items():
            for method, op in item.items():
                if method in HTTP_METHODS:
                    out.append((method, path, op, item))
        return out

    def envelope_data(self, schema: dict[str, Any]) -> dict[str, Any] | None:
        """The `data` schema of a success or list envelope."""
        merged = self.merged(self.resolve(schema)) if "$ref" in schema else self.merged(schema)
        data = merged.get("properties", {}).get("data")
        return data

    def run(self) -> str:
        for _method, _path, op, item in self.operations():
            if op["operationId"] == "createAccessToken":
                continue
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body is not None:
                self.named(ref_name(body["$ref"]), "param")
            for status, response in op.get("responses", {}).items():
                if not str(status).startswith("2"):
                    continue
                schema = (response.get("content") or {}).get("application/json", {}).get("schema")
                if schema is None:
                    continue
                data = self.envelope_data(schema)
                if data is None:
                    continue
                if data.get("type") == "array":
                    data = data["items"]
                if "$ref" in data:
                    self.named(ref_name(data["$ref"]), "model")
                elif data.get("properties"):
                    envelope = ref_name(schema["$ref"]).removesuffix("Envelope")
                    self.emit(self.fresh_name(envelope + "Result"), data, "model")
            self.query_params(op, item)
        for event_type, hook in self.spec.get("webhooks", {}).items():
            schema = hook["post"]["requestBody"]["content"]["application/json"]["schema"]
            self.event(event_type, ref_name(schema["$ref"]))
        return self.render()

    def query_params(self, op: dict[str, Any], item: dict[str, Any]) -> None:
        params = []
        for param in item.get("parameters", []) + op.get("parameters", []):
            if "$ref" in param:
                param = self.parameters[ref_name(param["$ref"])]
            if param.get("in") == "query":
                params.append(param)
        if not params:
            return
        name = pascal(op["operationId"]) + "Params"
        lines = [f"class {name}(TypedDict):"] + doc(f"The query of {op['operationId']}.", "    ")
        for param in params:
            override = self.api.query_overrides.get((op["operationId"], param["name"]))
            text = override or self.py_type(param["schema"], name, pascal(param["name"]), "param")
            lines.append(f"    {param['name']}: {text}" if param.get("required") else f"    {param['name']}: NotRequired[{text}]")
            lines += doc(param.get("description"), "    ")
        self.params[name] = lines

    def event(self, event_type: str, name: str) -> None:
        schema = self.merged(self.schemas[name])
        props = schema["properties"]
        data_name = self.fresh_name(name + "Data")
        self.emit(data_name, props["data"], "model", required_extra=self.api.always_present.get(name, []))
        lines = [f"class {name}(ReedsModel):"] + doc(self.schemas[name].get("description") or f"The {event_type} event.", "    ")
        lines += ["    id: str", '    """`evt_...`. Events can arrive more than once: skip ids you have processed."""']
        lines += [f"    type: Literal[{q(event_type)}]", "    created_at: str", "    livemode: bool", f"    data: {data_name}"]
        self.models[name] = lines
        self.events.append((event_type, name))

    # ------------------------------------------------------------ output

    def render(self) -> str:
        body: list[str] = []
        names: list[str] = []
        for name, definition in self.aliases.items():
            body += ["", f"{name}: TypeAlias = {definition}"]
            names.append(name)
        for store in (self.models, self.params):
            for name, lines in store.items():
                body += ["", ""] + lines
                names.append(name)
        title = pascal(self.api.name)
        body += ["", "", f"{title}Event: TypeAlias = {' | '.join(model for _, model in self.events)}"]
        body += [f'"""Every {title} API webhook event, by its `type`."""']
        body += ["", f"{self.api.name.upper()}_EVENTS: dict[str, type[ReedsModel]] = {{"]
        body += [f"    {q(event_type)}: {model}," for event_type, model in self.events]
        body += ["}", f'"""Each event type the {title} API sends, and its model."""']
        names += [f"{title}Event", f"{self.api.name.upper()}_EVENTS"]
        # isort-style, as ruff sorts __all__: CONSTANTS, then Classes, then the rest.
        order = sorted(names, key=lambda name: (0 if name.isupper() else 1 if name[:1].isupper() else 2, name))
        body += ["", "__all__ = ["] + [f"    {q(name)}," for name in order] + ["]", ""]
        text = "\n".join(body)
        # Imports from the code only, not the docstrings ("Any delivery..." isn't typing.Any).
        code = "\n".join(line for line in body if not line.strip().startswith('"""'))
        typing_names = [name for name in ("Any", "Literal", "TypeAlias", "Union") if re.search(rf"\b{name}\b", code)]
        extensions = [name for name in ("NotRequired", "TypedDict") if re.search(rf"\b{name}\b", code)]
        head = [
            f"# Generated by scripts/generate.py from {self.api.spec}. Do not edit: run `python scripts/generate.py`.",
            "# ruff: noqa: E501",
            "from __future__ import annotations",
            "",
        ]
        if "Sequence[" in code:
            head.append("from collections.abc import Sequence")
        if typing_names:
            head.append(f"from typing import {', '.join(typing_names)}")
        head.append("")
        if "Field(" in code:
            head.append("from pydantic import Field")
        if extensions:
            head.append(f"from typing_extensions import {', '.join(extensions)}")
        head += ["", "from .._models import ReedsModel", ""]
        return "\n".join(head) + text


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for api in APIS:
        text = Generator(api).run()
        target = ROOT / api.out
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                stale.append(api.out)
        else:
            target.write_text(text, encoding="utf-8")
            print(f"{api.spec} -> {api.out}")
    if stale:
        print("Out of date (run `python scripts/generate.py`): " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
