"""Turns JSON from the API into the library's models, without ever failing.

Reeds adds fields and enum values inside a version, and a response is still
the answer to a request that may have charged money. So parsing never raises:
it validates first (the normal case, every field typed), and if the data
doesn't fit the model it builds the objects field by field instead, keeping
what came.
"""

from __future__ import annotations

import types
from functools import cache
from typing import Annotated, Any, Literal, TypeVar, Union, cast, get_args, get_origin

import pydantic

T = TypeVar("T")

__all__ = ["parse"]


@cache
def _cached_adapter(tp: Any) -> pydantic.TypeAdapter[Any]:
    return pydantic.TypeAdapter(tp)


def _adapter(tp: Any) -> pydantic.TypeAdapter[Any]:
    """One TypeAdapter per type (building one is the slow part)."""
    try:
        return _cached_adapter(tp)
    except TypeError:  # an unhashable type
        return pydantic.TypeAdapter(tp)


def parse(tp: type[T] | Any, value: object) -> T:
    """``value`` as ``tp``: validated when it fits, built leniently when it doesn't."""
    try:
        return cast(T, _adapter(tp).validate_python(value))
    except pydantic.ValidationError:
        return cast(T, _construct(tp, value))


def _is_model(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, pydantic.BaseModel)


def _fits(tp: Any, value: object) -> bool:
    try:
        _adapter(tp).validate_python(value)
    except pydantic.ValidationError:
        return False
    return True


def _construct(tp: Any, value: object) -> Any:
    origin = get_origin(tp)
    if origin is Annotated:
        return _construct(get_args(tp)[0], value)
    if value is None or tp is Any:
        return value
    if _is_model(tp):
        return _construct_model(tp, value) if isinstance(value, dict) else value
    if origin is Union or origin is types.UnionType:
        return _construct_union(get_args(tp), value)
    if origin is list and isinstance(value, list):
        (item,) = get_args(tp) or (Any,)
        return [parse(item, entry) for entry in value]
    # Scalars, Literals, dicts: keep the value as it came.
    return value


def _construct_model(model: type[pydantic.BaseModel], value: dict[str, Any]) -> pydantic.BaseModel:
    fields: dict[str, Any] = {}
    used: set[str] = set()
    for name, info in model.model_fields.items():
        key = info.alias or name
        if key in value:
            fields[name] = parse(info.annotation, value[key])
            used.add(key)
    extra = {key: entry for key, entry in value.items() if key not in used}
    return model.model_construct(**{**extra, **fields})


def _literal_fields_match(model: type[pydantic.BaseModel], value: dict[str, Any]) -> bool:
    """True when every Literal-typed field the value carries has an allowed value (a discriminator)."""
    for name, info in model.model_fields.items():
        if get_origin(info.annotation) is Literal:
            key = info.alias or name
            if key in value and value[key] not in get_args(info.annotation):
                return False
    return True


def _construct_union(members: tuple[Any, ...], value: object) -> Any:
    for member in members:
        if member is not type(None) and _fits(member, value):
            return _adapter(member).validate_python(value)
    if isinstance(value, dict):
        models = [member for member in members if _is_model(member)]
        for model in models:
            if _literal_fields_match(model, value):
                return _construct_model(model, value)
        if models:
            return _construct_model(models[0], value)
    return value
