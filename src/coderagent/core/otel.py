"""The trace of a session, in the shape an OTel backend understands, and where it goes.

The event log stays the source of truth. This module only turns the events into
spans and hands them to an exporter. A backend that is down is a warning and
nothing more: the session does not care about the trace.
"""

import hashlib
import logging
from typing import Any, Protocol

from coderagent.core.events import Event, EventType

logger = logging.getLogger("coderagent.core.otel")

SCOPE = "coderagent"
DEFAULT_ENDPOINT = "http://localhost:4318/v1/traces"
"""Where a collector listens, when the user does not say."""


class Exporter(Protocol):
    """Where the spans of a session go."""

    def export(self, payload: dict[str, Any]) -> bool:
        """Send the trace. Returns whether it arrived."""


class OtlpExporter:
    """Sends the trace to an OTLP endpoint over HTTP."""

    def __init__(
        self, endpoint: str = DEFAULT_ENDPOINT, headers: dict[str, str] | None = None, timeout: float = 5.0
    ) -> None:
        self.endpoint = endpoint
        self.headers = headers or {}
        """The headers the backend wants, like the key it asks for."""
        self.timeout = timeout

    def export(self, payload: dict[str, Any]) -> bool:
        import requests

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json", **self.headers},
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            logger.warning("The trace did not reach %s: %s", self.endpoint, error)
            return False
        if response.status_code >= 400:
            logger.warning("%s refused the trace: %s", self.endpoint, response.status_code)
            return False
        return True


def build_trace(events: list[Event], session=None) -> dict[str, Any]:
    """The events of a session as OTLP/JSON.

    One span per turn, one per model call, one per tool call. The spans of a
    turn are children of that turn, and the turn is a child of nothing: the
    trace of a session is the trace of its id.
    """
    session_id = getattr(session, "id", "") or (events[0].session_id if events else "")
    trace_id = _hex(session_id, 32)
    spans: list[dict[str, Any]] = []
    turn: dict[str, Any] | None = None
    last = 0.0
    """The time of the event before the one at hand. A model call lasts until its answer."""
    tools: dict[str, dict[str, Any]] = {}
    """The span of every tool call, by the id of the call."""
    turn_ends: list[tuple[dict[str, Any], float]] = []
    """The span of every turn, with the time it was last heard from."""
    turn_done = True
    for event in events:
        timestamp = event.timestamp
        if event.type == EventType.USER_MESSAGE:
            if turn is not None and not turn_done:
                turn_ends.append((turn, last))
            turn = _span(trace_id, _hex(f"{session_id}:{timestamp}", 16), "turn", timestamp, timestamp)
            spans.append(turn)
            last = timestamp
            turn_done = False
            continue
        if turn is None:
            """What happened before the first turn is not part of a turn."""
            continue
        if event.type == EventType.ASSISTANT_MESSAGE:
            message = event.payload.get("message") or {}
            extra = message.get("extra") or {}
            spans.append(
                _span(
                    trace_id,
                    _hex(f"{session_id}:{timestamp}:model", 16),
                    "model",
                    last or timestamp,
                    timestamp,
                    parent=turn["spanId"],
                    attributes=[
                        _attr("model.name", extra.get("model", "")),
                        _attr("model.purpose", extra.get("purpose", "main")),
                        _attr("cost", float(extra.get("cost") or event.payload.get("cost") or 0.0)),
                        _attr("tokens.in", int(extra.get("tokens_in") or 0)),
                        _attr("tokens.out", int(extra.get("tokens_out") or 0)),
                    ],
                )
            )
            last = timestamp
        elif event.type == EventType.TOOL_CALL:
            for index, action in enumerate(event.payload.get("actions") or []):
                span = _span(
                    trace_id,
                    _hex(f"{session_id}:{timestamp}:{action.get('tool_call_id', index)}", 16),
                    f"tool.{action.get('tool', '')}",
                    timestamp,
                    timestamp,
                    parent=turn["spanId"],
                    attributes=[
                        _attr("tool.name", action.get("tool", "")),
                        _attr("tool.call_id", action.get("tool_call_id", "")),
                    ],
                )
                spans.append(span)
                tools[action.get("tool_call_id", "")] = span
            last = timestamp
        elif event.type == EventType.TOOL_RESULT:
            span = tools.get(event.payload.get("tool_call_id", ""))
            if span is not None:
                span["endTimeUnixNano"] = _nanos(timestamp)
                if event.payload.get("is_error"):
                    span["status"] = {"code": 2, "message": "the tool failed"}
            last = timestamp
        elif event.type == EventType.TURN_END:
            turn["endTimeUnixNano"] = _nanos(timestamp)
            turn["attributes"] += [
                _attr("turn.cost", float(event.payload.get("cost") or 0.0)),
                _attr("turn.stop_reason", event.payload.get("stop_reason", "")),
            ]
            last = timestamp
            turn_ends.append((turn, last))
            turn_done = True
        elif event.type == EventType.ERROR:
            turn["attributes"].append(_attr("error", event.payload.get("error", "")))
            turn["status"] = {"code": 2, "message": str(event.payload.get("error", ""))[:200]}
            last = timestamp
        else:
            turn["endTimeUnixNano"] = _nanos(timestamp)
            last = timestamp
    if turn is not None and not turn_done:
        turn_ends.append((turn, last))
    for span, end in turn_ends:
        if span["endTimeUnixNano"] == span["startTimeUnixNano"]:
            """A turn that never ended still has to have a length."""
            span["endTimeUnixNano"] = _nanos(end)
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attr("service.name", SCOPE),
                        _attr("session.id", session_id),
                        _attr("session.cwd", str(getattr(session, "cwd", ""))),
                        _attr("model.name", getattr(session, "model_name", "")),
                    ]
                },
                "scopeSpans": [{"scope": {"name": SCOPE}, "spans": spans}],
            }
        ]
    }


def _span(
    trace_id: str,
    span_id: str,
    name: str,
    start: float,
    end: float,
    parent: str = "",
    attributes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 1,
        "startTimeUnixNano": _nanos(start),
        "endTimeUnixNano": _nanos(end),
        "attributes": attributes or [],
    }
    if parent:
        span["parentSpanId"] = parent
    return span


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": value}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _hex(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def _nanos(timestamp: float) -> str:
    return str(int(timestamp * 1_000_000_000))


__all__ = ["DEFAULT_ENDPOINT", "Exporter", "OtlpExporter", "SCOPE", "build_trace"]
