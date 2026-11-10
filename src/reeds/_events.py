"""Webhook events from every Reeds API, parsed by their ``type``."""

from __future__ import annotations

from typing import Any, TypeAlias

from ._models import ReedsModel
from ._parse import parse
from .shipping._generated import SHIPPING_EVENTS, ShippingEvent

__all__ = ["EVENTS", "ReedsEvent", "UnknownEvent", "parse_event"]


class UnknownEvent(ReedsModel):
    """An event type this version of the library doesn't know yet. Reeds adds event types inside v1."""

    id: str
    type: str
    created_at: str
    livemode: bool
    data: dict[str, Any]


ReedsEvent: TypeAlias = ShippingEvent | UnknownEvent
"""Every webhook event any Reeds API sends. Each new API adds its events here.

Match on the class (``match event: case DeliveryBookedEvent(): ...``) or use
``isinstance``, and give the match a default branch: an event type this
version doesn't know arrives as an UnknownEvent.
"""

EVENTS: dict[str, type[ReedsModel]] = {**SHIPPING_EVENTS}
"""Each event type, and its model."""


def parse_event(data: object) -> ReedsEvent:
    event_type = data.get("type") if isinstance(data, dict) else None
    model = EVENTS.get(event_type, UnknownEvent) if isinstance(event_type, str) else UnknownEvent
    event: ReedsEvent = parse(model, data)
    return event
