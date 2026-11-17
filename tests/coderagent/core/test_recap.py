"""A recap summarizes the conversation without changing it."""

from pathlib import Path

from coderagent.config.schema import ContextConfig
from coderagent.core.context import ContextEngine
from coderagent.core.events import EventBus, EventType
from coderagent.core.session import SessionStore


class FakeModel:
    def __init__(self, answer: str = '{"goal": "the goal"}') -> None:
        self.answer = answer
        self.calls = 0
        self.total_cost = 0.0

    def complete(self, messages, **kwargs) -> str:
        self.calls += 1
        self.total_cost += 0.5
        return self.answer


class BrokenModel:
    def complete(self, messages, **kwargs) -> str:
        raise RuntimeError("no summary for you")


def make_engine(tmp_path: Path, model=None, **kwargs) -> ContextEngine:
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    return ContextEngine(
        session,
        store,
        EventBus(),
        kwargs.pop("config", ContextConfig()),
        model or FakeModel(),
        cwd=tmp_path,
        user_home=tmp_path / "home",
        **kwargs,
    )


def fill(engine: ContextEngine, turns: int) -> None:
    for index in range(turns):
        engine.append({"role": "user", "content": f"question {index}"})
        engine.append({"role": "assistant", "content": f"answer {index}"})


def test_a_recap_summarizes_without_dropping_anything(tmp_path):
    engine = make_engine(tmp_path)
    fill(engine, 4)
    before = list(engine.history.messages)
    summary = engine.recap()
    assert summary is not None
    assert summary.goal == "the goal"
    assert engine.history.messages == before


def test_a_recap_does_not_go_into_the_context_of_the_model(tmp_path):
    engine = make_engine(tmp_path)
    fill(engine, 2)
    engine.recap()
    assert engine.summary is None
    assert engine.summaries == []
    assert "the goal" not in str(engine.build_messages())


def test_a_recap_is_in_the_log(tmp_path):
    engine = make_engine(tmp_path)
    fill(engine, 2)
    events = []
    engine.bus.subscribe(EventType.RECAP, events.append)
    engine.recap()
    assert len(events) == 1
    assert events[0].payload["summary"]["goal"] == "the goal"
    assert events[0].payload["text"]
    assert events[0].payload["cost"] == 0.5
    assert any(event.type == EventType.RECAP for event in engine.store.events(engine.session.id))


def test_the_cost_of_a_recap_is_on_the_session(tmp_path):
    engine = make_engine(tmp_path)
    fill(engine, 2)
    engine.recap()
    assert engine.session.total_cost == 0.5


def test_a_recap_of_nothing_is_nothing(tmp_path):
    engine = make_engine(tmp_path)
    assert engine.recap() is None


def test_the_fallback_of_a_recap_does_not_say_that_the_messages_are_gone(tmp_path):
    engine = make_engine(tmp_path, model=BrokenModel())
    fill(engine, 2)
    summary = engine.recap()
    assert summary is not None
    assert summary.goal == "a recap of the conversation so far"
    assert summary.findings


def test_the_recap_of_a_conversation_that_was_compacted_knows_the_earlier_part(tmp_path):
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 4)
    assert engine.compact()
    summary = engine.recap()
    assert summary is not None
    assert "The earlier part of this conversation was compacted" in engine.summaries[0].render()
    assert len(engine.history.messages) == 2
