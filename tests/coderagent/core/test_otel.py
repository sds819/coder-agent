"""The trace of a session, in the shape an OTel backend understands, and where it goes."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from coderagent.core.events import Event, EventBus, EventType
from coderagent.core.loop import AgentLoop
from coderagent.core.otel import OtlpExporter, build_trace
from coderagent.core.session import SessionStore
from coderagent.models.gateway import ModelGateway
from coderagent.testing.factory import build_context, build_executor
from coderagent.testing.scripted_model import ScriptedModel


class _Collector(BaseHTTPRequestHandler):
    """A backend that keeps what it was sent."""

    payloads: list[dict] = []
    headers: dict[str, str] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", 0))
        type(self).payloads.append(json.loads(self.rfile.read(length)))
        type(self).headers = {key.lower(): value for key, value in self.headers.items()}
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args) -> None:
        """The test does not want the noise of the server."""


@contextmanager
def _backend():
    """A backend that listens, and the address it listens on."""
    _Collector.payloads = []
    _Collector.headers = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/traces"
    finally:
        server.shutdown()
        server.server_close()


def _spans(payload: dict) -> list[dict]:
    return payload["resourceSpans"][0]["scopeSpans"][0]["spans"]


def _attributes(span: dict) -> dict:
    return {attribute["key"]: attribute["value"] for attribute in span["attributes"]}


def _events(store: SessionStore, session, kind: str, payload: dict, timestamp: float) -> None:
    store.append(
        session.id,
        Event(type=kind, session_id=session.id, timestamp=timestamp, payload=payload),
    )


def _session(tmp_path):
    store = SessionStore(tmp_path)
    return store, store.create(tmp_path)


def _turn(store, session, start: float = 100.0) -> None:
    """One turn: a question, an answer, a tool and the end."""
    _events(store, session, EventType.USER_MESSAGE, {"content": "hi"}, start)
    _events(
        store,
        session,
        EventType.ASSISTANT_MESSAGE,
        {"message": {"extra": {"model": "test/model", "cost": 0.5, "tokens_in": 10, "tokens_out": 3}}},
        start + 1,
    )
    _events(store, session, EventType.TOOL_CALL, {"actions": [{"tool": "bash", "tool_call_id": "c1"}]}, start + 2)
    _events(store, session, EventType.TOOL_RESULT, {"tool": "bash", "tool_call_id": "c1"}, start + 3)
    _events(store, session, EventType.TURN_END, {"stop_reason": "end_turn", "cost": 0.5}, start + 4)


def test_a_turn_is_a_span_and_its_calls_are_its_children(tmp_path):
    store, session = _session(tmp_path)
    _turn(store, session)
    spans = _spans(build_trace(store.events(session.id), session))

    assert [span["name"] for span in spans] == ["turn", "model", "tool.bash"]
    assert spans[1]["parentSpanId"] == spans[0]["spanId"]
    assert spans[2]["parentSpanId"] == spans[0]["spanId"]
    assert "parentSpanId" not in spans[0]


def test_the_spans_are_flat(tmp_path):
    """OTLP has no spans inside a span: the children stand next to their parent."""
    store, session = _session(tmp_path)
    _turn(store, session)
    spans = _spans(build_trace(store.events(session.id), session))

    assert all("spans" not in span for span in spans)
    assert all(len(span["spanId"]) == 16 for span in spans)
    assert all(len(span["traceId"]) == 32 for span in spans)


def test_the_spans_of_a_session_share_the_trace(tmp_path):
    store, session = _session(tmp_path)
    _turn(store, session, 100.0)
    _turn(store, session, 200.0)
    spans = _spans(build_trace(store.events(session.id), session))

    assert len({span["traceId"] for span in spans}) == 1
    assert [span["name"] for span in spans].count("turn") == 2


def test_the_turn_carries_what_it_cost(tmp_path):
    store, session = _session(tmp_path)
    _turn(store, session)
    spans = _spans(build_trace(store.events(session.id), session))

    assert _attributes(spans[0])["turn.cost"]["doubleValue"] == 0.5
    assert _attributes(spans[0])["turn.stop_reason"]["stringValue"] == "end_turn"
    assert _attributes(spans[1])["model.name"]["stringValue"] == "test/model"
    assert _attributes(spans[1])["tokens.in"]["intValue"] == 10


def test_the_turn_has_a_length(tmp_path):
    store, session = _session(tmp_path)
    _turn(store, session, 100.0)
    spans = _spans(build_trace(store.events(session.id), session))

    assert spans[0]["startTimeUnixNano"] == "100000000000"
    assert spans[0]["endTimeUnixNano"] == "104000000000"
    assert spans[2]["endTimeUnixNano"] == "103000000000"


def test_a_tool_that_failed_says_so(tmp_path):
    store, session = _session(tmp_path)
    _events(store, session, EventType.USER_MESSAGE, {"content": "hi"}, 100.0)
    _events(store, session, EventType.TOOL_CALL, {"actions": [{"tool": "bash", "tool_call_id": "c1"}]}, 101.0)
    _events(store, session, EventType.TOOL_RESULT, {"tool": "bash", "tool_call_id": "c1", "is_error": True}, 102.0)
    spans = _spans(build_trace(store.events(session.id), session))

    assert spans[1]["status"]["code"] == 2


def test_what_happened_before_the_first_turn_is_not_a_turn(tmp_path):
    store, session = _session(tmp_path)
    """The session starts with the state of a session that has not begun."""
    spans = _spans(build_trace(store.events(session.id), session))

    assert spans == []


def test_the_trace_reaches_the_backend():
    with _backend() as endpoint:
        assert OtlpExporter(endpoint, {"x-key": "secret"}).export({"hello": "there"})

    assert _Collector.payloads == [{"hello": "there"}]
    assert _Collector.headers["x-key"] == "secret"


def test_a_backend_that_is_down_is_only_a_warning():
    """Nothing that is there to receive the trace: the session does not care."""
    assert not OtlpExporter("http://127.0.0.1:1/v1/traces", timeout=1).export({"hello": "there"})


def _loop(tmp_path, responses, exporter=None):
    store = SessionStore(tmp_path)
    session = store.create(tmp_path)
    bus = EventBus()
    model = ModelGateway(ScriptedModel(responses))
    executor = build_executor(tmp_path, store=store, context=build_context(tmp_path, session=session, bus=bus))
    loop = AgentLoop(
        model,
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
        exporter=exporter,
    )
    return loop, store, session


def _answer(content: str = "all done") -> dict:
    return {"role": "assistant", "content": content, "extra": {"cost": 0.1, "tokens_in": 5, "tokens_out": 2}}


def test_the_trace_of_a_turn_goes_to_the_backend(tmp_path):
    with _backend() as endpoint:
        loop, store, session = _loop(tmp_path, [_answer()], OtlpExporter(endpoint))
        loop.run_turn("say hello")

        assert len(_Collector.payloads) == 1
        spans = _spans(_Collector.payloads[0])
        assert [span["name"] for span in spans] == ["turn", "model"]
        assert _attributes(spans[0])["turn.stop_reason"]["stringValue"] == "end_turn"


def test_every_span_is_sent_once(tmp_path):
    with _backend() as endpoint:
        loop, store, session = _loop(tmp_path, [_answer(), _answer()], OtlpExporter(endpoint))
        loop.run_turn("first")
        loop.run_turn("second")

        assert len(_Collector.payloads) == 2
        assert [span["name"] for span in _spans(_Collector.payloads[1])] == ["turn", "model"]


def test_without_a_backend_the_session_does_not_look_for_one(tmp_path):
    loop, store, session = _loop(tmp_path, [_answer()])
    assert loop.run_turn("say hello").stop_reason == "end_turn"
