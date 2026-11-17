"""Compaction replaces the older part of the history with a summary."""

import json
import sys
from pathlib import Path

import pytest

from coderagent.config.schema import ContextConfig, HookCommand, HookConfig, HookMatcher
from coderagent.core.context import ContextEngine
from coderagent.core.events import EventBus, EventType
from coderagent.core.session import SessionStore
from coderagent.core.summarize import Summary
from coderagent.extensions.hooks import HookRunner


class FakeModel:
    def __init__(self, answer: str = '{"goal": "the goal"}') -> None:
        self.answer = answer
        self.calls = 0

    def complete(self, messages, **kwargs) -> str:
        self.calls += 1
        return self.answer


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


def test_compact_summarizes_the_older_turns_and_keeps_the_recent_ones(tmp_path):
    config = ContextConfig(keep_recent_turns=2, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 6)
    assert engine.compact()
    assert len(engine.history.messages) == 4
    assert engine.summary is not None
    assert engine.summary.goal == "the goal"


def test_compact_cuts_on_a_turn_boundary(tmp_path):
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    engine.append({"role": "user", "content": "q0"})
    engine.append({"role": "assistant", "content": "a0", "tool_calls": [{"id": "1", "function": {"name": "read"}}]})
    engine.append({"role": "tool", "tool_call_id": "1", "content": "content"})
    engine.append({"role": "user", "content": "q1"})
    assert engine.compact()
    assert engine.history.messages[0]["content"] == "q1"


def test_compact_of_an_empty_history_does_nothing(tmp_path):
    engine = make_engine(tmp_path)
    assert engine.compact() is False
    assert engine.summary is None


def test_compact_of_a_single_turn_does_nothing(tmp_path):
    config = ContextConfig(keep_recent_turns=5, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 1)
    assert engine.compact() is False


def test_the_context_is_compacted_before_the_kept_turns_are_used_up(tmp_path):
    """The default keeps 20 turns, but a session that is too big is compacted anyway."""
    config = ContextConfig(context_window=400, reserved_output=0, compact_threshold=0.5)
    engine = make_engine(tmp_path, config=config)
    for _ in range(3):
        engine.append({"role": "user", "content": "question " * 40})
        engine.append({"role": "assistant", "content": "answer " * 40})
    assert engine.maybe_compact()
    assert engine.summary is not None
    assert len(engine.history.messages) < 6


def test_a_turn_that_does_not_fit_is_cut_inside(tmp_path):
    """Even the last turn may be too big: then the cut is inside it."""
    config = ContextConfig(context_window=200, reserved_output=0, compact_threshold=0.5, keep_recent_turns=1)
    engine = make_engine(tmp_path, config=config)
    engine.append({"role": "user", "content": "q"})
    engine.append({"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "read"}}]})
    engine.append({"role": "tool", "tool_call_id": "1", "content": "x" * 4000})
    engine.append({"role": "assistant", "content": "the answer"})
    assert engine.maybe_compact()
    assert engine.summary is not None
    assert [message["content"] for message in engine.history.messages] == ["the answer"]
    """What the model sees is still a history that a provider accepts."""
    messages = engine.build_messages()
    assert messages[0]["role"] == "user"
    assert [message["role"] for message in messages[-2:]] == ["user", "assistant"]


def test_a_forced_compaction_cuts_even_when_the_window_fits(tmp_path):
    """The provider refused the context: the oldest turns go anyway."""
    config = ContextConfig(context_window=1000000)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 6)
    assert engine.compact() is False
    assert engine.force_compact()
    assert len(engine.history.messages) == 2


def test_compact_publishes_an_event_that_can_be_replayed(tmp_path):
    config = ContextConfig(keep_recent_turns=2, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 6)
    events = []
    engine.bus.subscribe(EventType.COMPACTION, events.append)
    assert engine.compact()
    assert len(events) == 1
    payload = events[0].payload
    assert payload["compacted_messages"] == 8
    assert payload["summary"]["goal"] == "the goal"


def test_restore_after_a_compaction_gives_the_same_view(tmp_path):
    config = ContextConfig(keep_recent_turns=2, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 6)
    engine.compact()
    messages = engine.history.messages
    summary = engine.summary

    restored = ContextEngine(engine.session, engine.store, EventBus(), config, FakeModel(), cwd=tmp_path)
    restored.restore()
    assert restored.history.messages == messages
    assert restored.summary == summary


def test_the_summary_model_is_used_and_the_fallback_takes_over_when_it_fails(tmp_path):
    class BrokenModel:
        def complete(self, messages, **kwargs) -> str:
            raise RuntimeError("no summary for you")

    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, model=BrokenModel(), config=config)
    fill(engine, 4)
    assert engine.compact()
    assert engine.summary.goal == "the earlier part of the conversation was compacted"
    assert engine.summary.findings


def test_a_summary_without_the_touched_files_is_rejected(tmp_path):
    class EmptyModel:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, **kwargs) -> str:
            self.calls += 1
            return '{"goal": "g", "files_touched": []}'

    model = EmptyModel()
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, model=model, config=config)
    engine.append({"role": "user", "content": "fix it"})
    engine.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "1", "function": {"name": "edit", "arguments": '{"path": "a.py"}'}}],
        }
    )
    engine.append({"role": "user", "content": "and now"})
    assert engine.compact()
    assert model.calls == 2
    assert engine.summary.goal != "g"


def test_maybe_compact_triggers_on_the_budget(tmp_path):
    config = ContextConfig(context_window=100, reserved_output=0, compact_threshold=0.5, keep_recent_turns=1)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 20)
    assert engine.maybe_compact()
    assert engine.summary is not None


def test_maybe_compact_does_nothing_when_the_budget_is_far_away(tmp_path):
    config = ContextConfig(context_window=100000, auto_compact=True)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 3)
    assert engine.maybe_compact() is False
    assert engine.summary is None


def test_the_schemas_of_the_tools_count_against_the_budget(tmp_path):
    """The tools are in every request, so a session with big schemas compacts sooner."""
    config = ContextConfig(context_window=1000, reserved_output=0, compact_threshold=0.5, keep_recent_turns=1)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 6)
    assert engine.maybe_compact() is False
    engine.tools = [{"name": "bash", "description": "x" * 4000, "parameters": {}}]
    assert engine.maybe_compact() is True
    assert engine.summary is not None


def test_the_schemas_of_the_tools_leave_less_room_for_the_history(tmp_path):
    """The kept window has to fit together with the schemas, not on its own."""
    config = ContextConfig(context_window=1000, reserved_output=0, compact_threshold=0.5, keep_recent_turns=1)
    plain = make_engine(tmp_path / "plain", config=config)
    with_tools = make_engine(tmp_path / "tools", config=config)
    with_tools.tools = [{"name": "bash", "description": "x" * 800, "parameters": {}}]
    for engine in (plain, with_tools):
        for index in range(20):
            engine.append({"role": "user", "content": f"question {index} " + "x" * 60})
            engine.append({"role": "assistant", "content": f"answer {index} " + "y" * 60})
    assert plain.compact()
    assert with_tools.compact()
    assert len(with_tools.history.messages) < len(plain.history.messages)


def test_a_restored_session_knows_when_it_compacted_last(tmp_path):
    """Without the turn of the last compaction, a restored session compacts again."""
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0, compact_every_turns=3)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 4)
    engine.session.turn_count = 5
    assert engine.compact()
    restored = ContextEngine(engine.session, engine.store, EventBus(), config, FakeModel(), cwd=tmp_path)
    restored.restore()
    assert restored.last_compact_turn == 5
    assert restored.maybe_compact() is False


def test_maybe_compact_can_be_switched_off(tmp_path):
    config = ContextConfig(context_window=100, reserved_output=0, compact_threshold=0.5, auto_compact=False)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 20)
    assert engine.maybe_compact() is False


def test_maybe_compact_triggers_on_the_turn_count(tmp_path):
    config = ContextConfig(context_window=1000000, compact_every_turns=3, keep_recent_turns=1)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 4)
    engine.session.turn_count = 4
    assert engine.maybe_compact()


def test_the_recent_errors_survive_the_compaction(tmp_path):
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    engine.append({"role": "user", "content": "q0"})
    engine.append({"role": "tool", "tool_call_id": "1", "content": "Error: the file was not found"})
    engine.append({"role": "user", "content": "q1"})
    assert engine.compact()
    assert engine.summary.recent_errors == ["Error: the file was not found"]
    assert "the file was not found" in engine.summary.render()


def test_the_summary_survives_a_round_trip_through_the_events(tmp_path):
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    fill(engine, 4)
    engine.compact()
    restored = ContextEngine(engine.session, engine.store, EventBus(), config, FakeModel(), cwd=tmp_path)
    restored.restore()
    assert isinstance(restored.summary, Summary)
    assert restored.summary.goal == "the goal"


def test_the_cost_of_the_summary_is_recorded_and_booked(tmp_path):
    """The summary is a model call, so it costs money and the session knows it."""

    class CostlyModel(FakeModel):
        def __init__(self) -> None:
            super().__init__()
            self.total_cost = 0.0

        def complete(self, messages, **kwargs) -> str:
            self.total_cost += 0.05
            return super().complete(messages, **kwargs)

    model = CostlyModel()
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, model=model, config=config)
    fill(engine, 4)
    assert engine.compact()
    events = engine.store.events(engine.session.id)
    assert [event.payload["cost"] for event in events if event.type == EventType.COMPACTION] == [0.05]


def test_the_event_says_how_much_of_the_history_the_summary_kept(tmp_path):
    """The ratio is the size of the summary against the size of what it replaces."""
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config)
    _fill_long(engine, 4)
    assert engine.compact()
    event = next(event for event in engine.store.events(engine.session.id) if event.type == EventType.COMPACTION)
    assert event.payload["tokens"] > 0
    assert event.payload["summary_tokens"] > 0
    assert event.payload["summary_ratio"] == pytest.approx(
        event.payload["summary_tokens"] / event.payload["tokens"], abs=0.001
    )


class ChunkModel:
    """Answers with a summary per chunk, and merges the partial ones."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, messages, **kwargs) -> str:
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        if "merging the partial summaries" in prompt:
            return '{"goal": "merged", "findings": ["all of it"]}'
        return json.dumps({"goal": "chunk", "findings": [f"finding {len(self.prompts)}"]})


def _fill_long(engine: ContextEngine, turns: int) -> None:
    for index in range(turns):
        engine.append({"role": "user", "content": f"question {index} " + "x" * 400})
        engine.append({"role": "assistant", "content": f"answer {index} " + "y" * 400})


def test_a_history_that_does_not_fit_is_summarized_in_chunks_and_merged(tmp_path):
    """One prompt per chunk, and one prompt that merges the partial summaries."""
    model = ChunkModel()
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0, summary_chunk_tokens=300)
    engine = make_engine(tmp_path, model=model, config=config)
    _fill_long(engine, 6)
    assert engine.compact()
    assert len(model.prompts) == 6, "five chunks and one merge"
    assert model.prompts[0].count("question ") == 1, "a chunk holds one turn"
    merge = model.prompts[-1]
    assert "finding 1" in merge and "finding 5" in merge, "the merge sees every partial summary"
    assert engine.summary.goal == "merged"


def test_the_partial_summaries_are_kept_when_the_merge_fails(tmp_path):
    """The fallback of the merge loses nothing: it puts the partial summaries together."""

    class BrokenMerge(ChunkModel):
        def complete(self, messages, **kwargs) -> str:
            if "merging the partial summaries" in messages[0]["content"]:
                raise RuntimeError("no merge for you")
            return super().complete(messages, **kwargs)

    model = BrokenMerge()
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0, summary_chunk_tokens=300)
    engine = make_engine(tmp_path, model=model, config=config)
    _fill_long(engine, 6)
    assert engine.compact()
    assert engine.summary.findings == ["finding 1", "finding 2", "finding 3", "finding 4", "finding 5"]


def test_the_previous_summary_is_part_of_the_merge(tmp_path):
    """A second compaction does not lose what the first one found."""
    model = ChunkModel()
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0, summary_chunk_tokens=300)
    engine = make_engine(tmp_path, model=model, config=config)
    _fill_long(engine, 6)
    engine.compact()
    engine.summaries = [Summary(goal="the old goal", findings=["the old finding"])]
    _fill_long(engine, 2)
    engine.compact()
    merge = model.prompts[-1]
    assert "the old finding" in merge


def _recorder(tmp_path: Path, name: str) -> str:
    """A hook command that writes the payload it gets into a file."""
    path = tmp_path / f"{name}.py"
    path.write_text(f"import sys\nopen({name + '.json'!r}, 'w').write(sys.stdin.read())\n", encoding="utf-8")
    return f"{sys.executable} {path}"


def test_the_hooks_see_the_compaction_and_its_result(tmp_path):
    """One hook sees the messages that go away, the other the summary that comes."""
    hooks = HookRunner(
        HookConfig(
            events={
                "PreCompact": [HookMatcher(hooks=[HookCommand(command=_recorder(tmp_path, "pre"))])],
                "PostCompact": [HookMatcher(hooks=[HookCommand(command=_recorder(tmp_path, "post"))])],
            }
        ),
        tmp_path,
    )
    config = ContextConfig(keep_recent_turns=1, keep_recent_token_ratio=0.0)
    engine = make_engine(tmp_path, config=config, hooks=hooks)
    fill(engine, 4)
    assert engine.compact()
    pre = json.loads((tmp_path / "pre.json").read_text(encoding="utf-8"))
    post = json.loads((tmp_path / "post.json").read_text(encoding="utf-8"))
    assert len(pre["messages"]) == 6
    assert pre["messages"][0]["content"] == "question 0"
    assert pre["turn"] == engine.session.turn_count
    assert post["summary"]
    assert post["messages"] == len(pre["messages"])
    assert post["tokens"] > 0 and post["summary_tokens"] > 0
