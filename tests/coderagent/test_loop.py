import json
import logging

import pytest

from coderagent.core.events import EventBus, EventType
from coderagent.core.loop import AgentLoop, stop_note
from coderagent.core.session import SessionState, SessionStore
from coderagent.models.gateway import ModelGateway
from coderagent.testing.factory import AllowAllApprover, build_context, build_executor
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.tools.permissions import PermissionMode, PermissionPolicy


def _bash_call(command: str, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "bash", "arguments": json.dumps({"command": command})},
    }


def _assistant(content: str = "", tool_calls: list[dict] | None = None, cost: float = 0.0, tokens: int = 0) -> dict:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls or [],
        "extra": {"cost": cost, "tokens_in": tokens, "tokens_out": 0},
    }


def _loop(tmp_path, responses, **kwargs):
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
        **kwargs,
    )
    return loop, store, session, bus


def test_turn_executes_tool_call_and_finishes(tmp_path):
    loop, store, session, _ = _loop(
        tmp_path,
        [
            _assistant(tool_calls=[_bash_call("echo hello")], cost=0.1),
            _assistant(content="all done", cost=0.2),
        ],
    )
    result = loop.run_turn("say hello")

    assert result.stop_reason == "end_turn"
    assert result.cost == pytest.approx(0.3)
    assert [message["role"] for message in result.messages] == ["user", "assistant", "tool", "assistant"]
    assert "hello" in result.messages[2]["content"]
    assert result.messages[2]["tool_call_id"] == "call_1"

    events = store.events(session.id)
    assert [event.type for event in events] == [
        EventType.STATE_CHANGE,
        EventType.USER_MESSAGE,
        EventType.STATE_CHANGE,
        EventType.ASSISTANT_MESSAGE,
        EventType.STATE_CHANGE,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.TOOL_RESULT,
        EventType.STATE_CHANGE,
        EventType.ASSISTANT_MESSAGE,
        EventType.TURN_END,
        EventType.STATE_CHANGE,
    ]
    """The result of the tool is in the log twice: once with the tool and the diff, once with the message."""
    assert store.rebuild(session.id).state == SessionState.DONE
    assert store.rebuild(session.id).metadata["stop_reason"] == "end_turn"


def test_max_turns_stops_the_loop(tmp_path):
    loop, _, _, _ = _loop(
        tmp_path,
        [_assistant(tool_calls=[_bash_call("echo hi")]) for _ in range(5)],
        max_turns=2,
    )
    result = loop.run_turn("loop forever")
    assert result.stop_reason == "max_turns"


def test_a_turn_that_was_cut_off_says_why():
    assert stop_note("max_turns", 50) == "the turn was cut off: it reached the ceiling of 50 model calls"
    assert stop_note("cost_exceeded") == "the turn stopped: the budget of the session is spent"
    assert stop_note("token_limit") == "the turn stopped: the token limit of the session is reached"
    assert stop_note("end_turn") == ""


def test_the_reason_a_turn_ended_is_in_the_log(tmp_path):
    loop, store, session, _ = _loop(
        tmp_path,
        [_assistant(tool_calls=[_bash_call("echo hi")]) for _ in range(5)],
        max_turns=2,
    )
    loop.run_turn("loop forever")

    ends = [event for event in store.events(session.id) if event.type == EventType.TURN_END]
    assert [event.payload["stop_reason"] for event in ends] == ["max_turns"]
    assert store.rebuild(session.id).metadata["stop_reason"] == "max_turns"


def test_an_interrupted_turn_says_so_in_the_log(tmp_path):
    loop, store, session, _ = _loop(tmp_path, [_assistant(content="never reached")])
    loop.cancel = lambda: True
    loop.run_turn("stop me")

    ends = [event for event in store.events(session.id) if event.type == EventType.TURN_END]
    assert [event.payload["stop_reason"] for event in ends] == ["interrupted"]


def test_the_session_waits_for_the_approval(tmp_path):
    store = SessionStore(tmp_path)
    session = store.create(tmp_path)
    bus = EventBus()
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
    executor = build_executor(
        tmp_path,
        approver=AllowAllApprover(),
        store=store,
        context=build_context(tmp_path, session=session, bus=bus, policy=policy),
    )
    loop = AgentLoop(
        ModelGateway(
            ScriptedModel([_assistant(tool_calls=[_bash_call("sh -c 'echo hi'")]), _assistant(content="done")])
        ),
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
    )
    loop.run_turn("run it")

    states = [event.payload.get("state") for event in store.events(session.id) if event.type == EventType.STATE_CHANGE]
    assert "awaiting_approval" in states
    assert states.index("awaiting_approval") < len(states) - 1


def test_cost_limit_stops_the_loop(tmp_path):
    loop, _, _, _ = _loop(
        tmp_path,
        [_assistant(tool_calls=[_bash_call("echo hi")], cost=1.0) for _ in range(5)],
        cost_limit=1.5,
    )
    result = loop.run_turn("spend money")
    assert result.stop_reason == "cost_exceeded"


def test_the_token_budget_stops_a_model_that_has_no_price(tmp_path):
    """The money of a model without a price never moves, so the tokens are the budget."""
    loop, store, session, _ = _loop(
        tmp_path,
        [_assistant(tool_calls=[_bash_call("echo hi")], tokens=100) for _ in range(5)],
        token_limit=150,
    )
    result = loop.run_turn("spend tokens")
    assert result.stop_reason == "token_limit"
    assert store.rebuild(session.id).total_tokens == 200


def test_a_cost_limit_that_cannot_be_enforced_is_reported(tmp_path, caplog):
    loop, _, _, _ = _loop(
        tmp_path,
        [_assistant(content="done", tokens=100)],
        cost_limit=1.0,
    )
    with caplog.at_level(logging.WARNING):
        loop.run_turn("spend money")
    assert "token_limit" in caplog.text


def test_no_warning_when_the_model_has_a_price(tmp_path, caplog):
    loop, _, _, _ = _loop(
        tmp_path,
        [_assistant(content="done", cost=0.5, tokens=100)],
        cost_limit=1.0,
    )
    with caplog.at_level(logging.WARNING):
        loop.run_turn("spend money")
    assert "token_limit" not in caplog.text


def test_model_error_is_reported(tmp_path):
    loop, store, session, bus = _loop(tmp_path, [])
    result = loop.run_turn("trigger an error")
    assert result.stop_reason == "error"
    assert "AssertionError" in result.error
    assert any(event.type == EventType.ERROR for event in store.events(session.id))
    assert store.rebuild(session.id).state == SessionState.ERROR


def test_the_diff_of_a_review_does_not_stay_in_the_context(tmp_path):
    """The diff is read once. The rest of the session does not have to carry it."""
    loop, store, session, _ = _loop(tmp_path, [_assistant(content="the review")])
    loop.run_turn("the diff of the changes", purpose="review")
    assert "the diff of the changes" not in json.dumps(loop.messages)
    assert "not in the context anymore" in loop.messages[0]["content"]


def test_the_model_sees_the_diff_of_the_review(tmp_path):
    loop, _, _, _ = _loop(tmp_path, [_assistant(content="the review")])
    loop.run_turn("the diff of the changes", purpose="review")
    assert "the diff of the changes" in json.dumps(loop.model.backend.calls[0])


def test_the_diff_of_a_review_is_not_in_the_log(tmp_path):
    loop, store, session, _ = _loop(tmp_path, [_assistant(content="the review")])
    loop.run_turn("the diff of the changes", purpose="review")
    events = [event for event in store.events(session.id) if event.type == EventType.USER_MESSAGE]
    assert "the diff of the changes" not in json.dumps(events[0].payload)


def test_an_ordinary_message_stays_in_the_context(tmp_path):
    loop, _, _, _ = _loop(tmp_path, [_assistant(content="done")])
    loop.run_turn("say hello")
    assert loop.messages[0]["content"] == "say hello"


def test_conversation_is_restored_from_the_event_log(tmp_path):
    loop, store, session, _ = _loop(tmp_path, [_assistant(content="done", cost=0.5)])
    loop.run_turn("first question")

    executor = build_executor(tmp_path)
    resumed = AgentLoop(
        ModelGateway(ScriptedModel([_assistant(content="still here")])),
        executor,
        store.rebuild(session.id),
        store,
        EventBus(),
        tools=executor.registry.schemas(),
    )
    assert [message["content"] for message in resumed.messages] == ["first question", "done"]
    result = resumed.run_turn("second question")
    assert result.messages[0] == {"role": "user", "content": "second question"}
    assert store.rebuild(session.id).turn_count == 2


def test_a_message_with_an_image_reaches_the_model(tmp_path):
    """The model sees the image as a part of the message."""
    from coderagent.core.content import parts

    loop, store, session, _ = _loop(tmp_path, [_assistant(content="done")])
    url = "data:image/png;base64,AAAA"
    loop.run_turn(parts("what is this?", [url]))

    assert loop.model.backend.calls[0][-1]["content"] == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": url}},
    ]
    users = [event for event in store.events(session.id) if event.type == EventType.USER_MESSAGE]
    assert users[0].payload["content"][1]["image_url"]["url"] == url


def test_a_message_with_an_image_survives_a_restart(tmp_path):
    """The event log keeps the image, so the session can be continued."""
    from coderagent.core.content import parts

    loop, store, session, _ = _loop(tmp_path, [_assistant(content="done")])
    url = "data:image/png;base64,AAAA"
    loop.run_turn(parts("what is this?", [url]))

    executor = build_executor(tmp_path)
    resumed = AgentLoop(
        ModelGateway(ScriptedModel([_assistant(content="still here")])),
        executor,
        store.rebuild(session.id),
        store,
        EventBus(),
        tools=executor.registry.schemas(),
    )
    assert resumed.messages[0]["content"][1]["image_url"]["url"] == url


def test_the_tools_of_the_session_know_when_the_turn_is_interrupted(tmp_path):
    from coderagent.config.schema import Config
    from coderagent.run import build_loop

    loop = build_loop(Config(), tmp_path, model=ScriptedModel([_assistant(content="hi")]))
    assert loop.executor.ctx_factory().cancel() is False
    loop.cancel = lambda: True
    assert loop.executor.ctx_factory().cancel() is True


def test_a_command_that_is_interrupted_ends_the_turn(tmp_path):
    from coderagent.config.schema import Config
    from coderagent.run import build_loop

    marker = tmp_path / "started"
    loop = build_loop(
        Config(),
        tmp_path,
        model=ScriptedModel([_assistant(tool_calls=[_bash_call(f"touch {marker}; sleep 30")])]),
        permission_mode="bypass",
    )

    def cancel() -> bool:
        """The turn is stopped once the command runs, not before it starts."""
        return marker.exists()

    loop.cancel = cancel
    result = loop.run_turn("run something long")

    assert result.stop_reason == "interrupted"
    assert "[interrupted]" in result.messages[-1]["content"]


def test_the_turn_is_stopped_while_the_model_answers(tmp_path):
    """Ctrl+C cuts the answer of the model short: the user does not wait for the rest."""
    from coderagent.models.streaming import ModelEvent

    class Chatty:
        model_name = "chatty"

        def query_stream(self, messages, tools=None, **kwargs):
            for index in range(5):
                yield ModelEvent(type="text", content=f"part {index} ")

        def get_template_vars(self):
            return {"model_name": "chatty"}

    store = SessionStore(tmp_path)
    session = store.create(tmp_path)
    bus = EventBus()
    executor = build_executor(tmp_path, store=store, context=build_context(tmp_path, session=session, bus=bus))
    loop = AgentLoop(ModelGateway(Chatty()), executor, session, store, bus, tools=executor.registry.schemas())
    seen: list[int] = []

    def cancel() -> bool:
        seen.append(1)
        return len(seen) > 1

    loop.cancel = cancel
    result = loop.run_turn("say hello")

    assert result.stop_reason == "interrupted"
    assert not any(message.get("role") == "assistant" for message in result.messages)
    """The half answer is not kept: the model has to answer again."""
