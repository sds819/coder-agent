"""The events of the core, as the items the browser renders."""

import pytest

from coderagent.core.events import Event, EventType
from coderagent.web.events import normalize


def _event(event_type: EventType, payload: dict) -> Event:
    return Event(type=event_type, session_id="s1", timestamp=1.0, payload=payload)


def test_a_reflection_of_a_model_without_a_price_says_so():
    """The money of a model without a price is unknown, not zero."""
    items = normalize(_event(EventType.REFLECTION, {"cost": 0.0, "priced": False, "model": "m1"}))

    assert items[0]["kind"] == "reflection"
    assert items[0]["priced"] is False


def test_a_reflection_of_a_priced_model_says_nothing_about_it():
    items = normalize(_event(EventType.REFLECTION, {"cost": 0.5, "priced": True, "model": "m1"}))

    assert items[0]["priced"] is True
    assert items[0]["cost"] == pytest.approx(0.5)


def test_the_reason_a_turn_ended_is_an_item():
    items = normalize(_event(EventType.TURN_END, {"stop_reason": "max_turns", "calls": 100, "error": ""}))

    assert items[0] == {"kind": "turn_stopped", "stop_reason": "max_turns", "calls": 100, "error": ""}
