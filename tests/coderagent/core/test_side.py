"""A conversation that goes aside: its own session, the main one untouched."""

from pathlib import Path

from coderagent.config.schema import Config
from coderagent.core.events import EventBus, EventType
from coderagent.core.session import SessionStore
from coderagent.run import build_loop
from coderagent.testing.scripted_model import ScriptedModel


def _loop(tmp_path: Path, responses=None):
    store = SessionStore(tmp_path / "sessions")
    loop = build_loop(
        Config(),
        tmp_path,
        model=ScriptedModel(responses or [{"role": "assistant", "content": "the answer"}]),
        store=store,
        bus=EventBus(),
    )
    return loop, store


def _tools(events) -> list[str]:
    """The tools whose result is in these events."""
    return [event.payload.get("tool", "") for event in events if event.type == EventType.TOOL_RESULT]


def test_a_side_conversation_runs_in_a_session_of_its_own(tmp_path):
    loop, store = _loop(tmp_path)
    side = store.side(loop.session.id)
    result = loop.run_turn("what does this do?", "side", side)
    assert result.session_id == side.id
    assert result.stop_reason == "end_turn"
    assert loop.session.id != side.id


def test_the_main_conversation_is_not_touched(tmp_path):
    loop, store = _loop(tmp_path)
    side = store.side(loop.session.id)
    loop.run_turn("what does this do?", "side", side)
    assert loop.context.history.messages == []
    assert len(loop.messages) == 0
    assert [event.type for event in store.events(loop.session.id)] == [
        EventType.STATE_CHANGE,
        EventType.SIDE_CONVERSATION,
    ]


def test_the_side_conversation_is_in_the_log_of_the_main_session(tmp_path):
    loop, store = _loop(tmp_path)
    side = store.side(loop.session.id)
    loop.run_turn("what does this do?", "side", side)
    events = [event for event in store.events(loop.session.id) if event.type == EventType.SIDE_CONVERSATION]
    assert len(events) == 1
    assert events[0].payload["question"] == "what does this do?"
    assert events[0].payload["answer"] == "the answer"
    assert events[0].payload["session_id"] == side.id


def test_the_side_session_knows_its_parent(tmp_path):
    loop, store = _loop(tmp_path)
    side = store.side(loop.session.id)
    assert side.metadata["parent"] == loop.session.id


def test_the_tools_of_the_side_conversation_land_in_the_side_session(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    loop, store = _loop(
        tmp_path,
        responses=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "1", "function": {"name": "read", "arguments": '{"path": "a.txt"}'}}],
            },
            {"role": "assistant", "content": "done"},
        ],
    )
    side = store.side(loop.session.id)
    loop.run_turn("read the file", "side", side)
    assert "read" in _tools(store.events(side.id))
    assert "read" not in _tools(store.events(loop.session.id))


def test_the_answer_of_a_side_conversation_is_in_its_own_log(tmp_path):
    loop, store = _loop(tmp_path)
    side = store.side(loop.session.id)
    loop.run_turn("what does this do?", "side", side)
    answers = [
        event.payload.get("message", {}).get("content")
        for event in store.events(side.id)
        if event.type == EventType.ASSISTANT_MESSAGE
    ]
    assert answers == ["the answer"]
