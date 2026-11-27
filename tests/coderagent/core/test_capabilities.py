"""What the model can take: the agent asks before it sends a picture."""

import pytest
from pydantic import ValidationError

from coderagent.config.schema import ModelConfig
from coderagent.core.capabilities import probe, support
from coderagent.core.events import EventBus, EventType
from coderagent.core.loop import AgentLoop
from coderagent.core.session import SessionStore
from coderagent.models.gateway import ModelGateway
from coderagent.testing.factory import AllowAllApprover, build_context, build_executor
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.tools.permissions import PermissionMode, PermissionPolicy

PICTURE = [
    {"type": "text", "text": "what is this"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
]


def _assistant(content: str = "") -> dict:
    return {"role": "assistant", "content": content, "tool_calls": [], "extra": {"cost": 0.0}}


def _loop(tmp_path, responses, capabilities=None, remember=None):
    store = SessionStore(tmp_path)
    session = store.create(tmp_path)
    bus = EventBus()
    model = ModelGateway(ScriptedModel(responses))
    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path)
    context = build_context(tmp_path, session=session, bus=bus, policy=policy)
    executor = build_executor(tmp_path, store=store, context=context, approver=AllowAllApprover())
    loop = AgentLoop(
        model,
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
        capabilities=capabilities or {},
        remember=remember,
    )
    return loop, store, session


def test_a_model_that_cannot_see_pictures_refuses_the_turn(tmp_path):
    loop, store, session = _loop(tmp_path, [_assistant("a red square")], {"scripted": {"image": False}})

    result = loop.run_turn(PICTURE)

    assert result.stop_reason == "error"
    assert "cannot take pictures" in result.error
    assert "scripted" in result.error
    assert loop.model.n_calls == 0
    assert [event.type for event in store.events(session.id)][-2:] == [EventType.ERROR, EventType.TURN_END]


def test_the_picture_stays_out_of_the_context_when_the_turn_is_refused(tmp_path):
    loop, _, _ = _loop(tmp_path, [_assistant("a red square")], {"scripted": {"image": False}})

    loop.run_turn(PICTURE)

    assert all(isinstance(message["content"], str) for message in loop.context.history.messages)
    assert "image_url" not in str(loop.context.history.messages)


def test_a_model_that_sees_pictures_answers_the_turn(tmp_path):
    loop, _, _ = _loop(tmp_path, [_assistant("a red square")], {"scripted": {"image": True}})

    result = loop.run_turn(PICTURE)

    assert result.stop_reason == "end_turn"
    assert result.messages[-1]["content"] == "a red square"
    assert "image_url" in str(loop.model.backend.calls[0])


def test_a_model_that_nobody_knows_about_is_asked_first(tmp_path):
    """Nobody said what the model takes, so the agent asks it."""
    loop, _, _ = _loop(tmp_path, [_assistant("magenta"), _assistant("a red square")])

    result = loop.run_turn(PICTURE)

    assert result.stop_reason == "end_turn"
    assert result.messages[-1]["content"] == "a red square"
    assert loop.model.n_calls == 2
    assert "What color is this picture?" in loop.model.backend.calls[0][0]["content"][0]["text"]


def test_the_answer_of_the_probe_is_remembered(tmp_path):
    remembered = []
    loop, _, _ = _loop(
        tmp_path,
        [_assistant("magenta"), _assistant("a red square")],
        remember=lambda *args: remembered.append(args),
    )

    loop.run_turn(PICTURE)

    assert remembered == [("scripted", "image", True)]
    assert loop.capabilities == {"scripted": {"image": True}}


def test_a_model_that_does_not_see_pictures_is_refused_after_the_probe(tmp_path):
    loop, _, _ = _loop(tmp_path, [_assistant("I cannot see the picture")])

    result = loop.run_turn(PICTURE)

    assert result.stop_reason == "error"
    assert "cannot take pictures" in result.error
    assert loop.model.n_calls == 1


def test_nobody_knows_when_the_model_does_not_answer_the_probe(tmp_path):
    loop, _, _ = _loop(tmp_path, [_assistant(""), _assistant("")])

    result = loop.run_turn(PICTURE)

    assert result.stop_reason == "error"
    assert "Nobody knows" in result.error
    assert "model.capabilities" in result.error
    assert loop.model.n_calls == 2


def test_a_model_that_did_not_answer_is_not_asked_again(tmp_path):
    loop, _, _ = _loop(tmp_path, [_assistant(""), _assistant("")])

    loop.run_turn(PICTURE)
    result = loop.run_turn(PICTURE)

    assert "Nobody knows" in result.error
    assert loop.model.n_calls == 2


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("magenta", True), ("It is purple", True), ("a red square", False), ("", None)],
)
def test_the_probe_asks_a_picture_of_one_color(answer, expected):
    said = probe(lambda messages: answer, "image")

    assert said is expected


def test_the_probe_says_no_when_the_provider_refuses_the_picture():
    def refuse(messages):
        raise RuntimeError("this model does not support image input")

    assert probe(refuse, "image") is False


def test_the_probe_says_nothing_when_the_call_fails():
    def fail(messages):
        raise RuntimeError("the connection is down")

    assert probe(fail, "image") is None


def test_the_probe_asks_nothing_about_the_sound():
    assert probe(lambda messages: "yes", "audio") is None


def test_a_turn_without_a_picture_is_never_refused(tmp_path):
    loop, _, _ = _loop(tmp_path, [_assistant("all done")])

    result = loop.run_turn("say hello")

    assert result.stop_reason == "end_turn"
    assert result.messages[-1]["content"] == "all done"


def test_litellm_says_what_a_known_model_takes():
    assert support(["gpt-4o"], "image") is True
    assert support(["no/such-model"], "image") is None


def test_what_the_user_says_wins_over_litellm():
    assert support(["gpt-4o"], "image", {"gpt-4o": {"image": False}}) is False
    assert support(["no/such-model"], "image", {"no/such-model": {"image": True}}) is True


def test_the_configuration_refuses_an_unknown_kind_of_content():
    with pytest.raises(ValidationError, match="unknown kind of content"):
        ModelConfig(capabilities={"my/model": {"picture": True}})
