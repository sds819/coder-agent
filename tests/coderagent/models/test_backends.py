"""The response is normalized into the message shape the loop expects."""

import litellm
import pytest

from coderagent.models.backends import LiteLLMBackend, is_auth_error
from coderagent.models.streaming import ModelEvent, message_from_events


class _Delta:
    def __init__(self, **fields) -> None:
        self.__dict__.update(fields)


class _Choice:
    def __init__(self, delta) -> None:
        self.delta = delta


class _Chunk:
    def __init__(self, content=None, reasoning_content=None, tool_calls=None, usage=None) -> None:
        self.choices = [_Choice(_Delta(content=content, reasoning_content=reasoning_content, tool_calls=tool_calls))]
        self.usage = usage


def test_a_message_without_tool_calls_has_no_tool_calls_key():
    message = message_from_events([ModelEvent(type="text", content="hello")])
    assert message == {"role": "assistant", "content": "hello", "extra": {"cost": 0.0, "tokens_in": 0, "tokens_out": 0}}


def test_the_tokens_of_the_usage_are_kept():
    message = message_from_events(
        [ModelEvent(type="usage", cost=0.5, raw={"usage": {"prompt_tokens": 120, "completion_tokens": 30}})]
    )
    assert message["extra"]["tokens_in"] == 120
    assert message["extra"]["tokens_out"] == 30
    assert message["extra"]["cost"] == 0.5


def test_the_tool_calls_are_kept_when_they_exist():
    call = {"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}}
    message = message_from_events([ModelEvent(type="tool_call_done", tool_call=call)])
    assert message["tool_calls"] == [call]
    assert message["content"] == ""


def test_the_reasoning_is_kept_out_of_the_text():
    message = message_from_events(
        [ModelEvent(type="reasoning", content="thinking"), ModelEvent(type="text", content="answer")]
    )
    assert message["content"] == "answer"
    assert message["extra"]["reasoning"] == "thinking"


def test_the_cost_is_booked():
    message = message_from_events([ModelEvent(type="text", content="hi"), ModelEvent(type="usage", cost=0.25)])
    assert message["extra"]["cost"] == 0.25


def test_the_backend_reads_the_events_of_a_stream():
    backend = LiteLLMBackend("test/model")
    chunks = [
        _Chunk(content="he", reasoning_content="think"),
        _Chunk(content="llo", tool_calls=[{"index": 0, "id": "c1", "function": {"name": "read", "arguments": '{"pa'}}]),
        _Chunk(tool_calls=[{"index": 0, "function": {"arguments": 'th": "a.py"}'}}]),
    ]
    events = list(backend._events(chunks))
    assert [event.type for event in events] == [
        "reasoning",
        "text",
        "text",
        "tool_call_delta",
        "tool_call_delta",
        "tool_call_done",
    ]
    assert events[-1].tool_call == {
        "id": "c1",
        "type": "function",
        "function": {"name": "read", "arguments": '{"path": "a.py"}'},
    }


def test_the_text_of_a_stream_becomes_one_message():
    backend = LiteLLMBackend("test/model")
    chunks = [_Chunk(content="he"), _Chunk(content="llo")]
    message = message_from_events(backend._events(chunks))
    assert message["content"] == "hello"


def test_a_model_without_a_price_is_complained_about_once(caplog):
    """The warning would come with every call, and it is the same every time."""
    from coderagent.models.backends import _warn_about_the_price

    _warn_about_the_price.cache_clear()
    with caplog.at_level("WARNING", logger="coderagent.backend"):
        _warn_about_the_price("openai/SomeModel", "no price")
        _warn_about_the_price("openai/SomeModel", "no price")
    assert len(caplog.records) == 1
    assert "openai/SomeModel" in caplog.records[0].getMessage()


def test_the_text_of_an_error_says_whether_the_key_is_the_problem():
    assert is_auth_error(Exception("Invalid token: no api key given"))
    assert is_auth_error(Exception("Authentication failed"))
    assert not is_auth_error(Exception("the server is busy"))


def test_a_wrong_key_fails_at_once_and_does_not_wait_for_the_retries(monkeypatch):
    """A relay station without a key answers with a 500. Waiting does not make the key good."""
    calls: list[dict] = []

    def completion(**kwargs):
        calls.append(kwargs)
        raise litellm.exceptions.InternalServerError("Invalid token: no api key", "openai", "test/model")

    monkeypatch.setattr(litellm, "completion", completion)
    with pytest.raises(litellm.exceptions.AuthenticationError):
        LiteLLMBackend("test/model")._open_stream([{"role": "user", "content": "hi"}], {})
    assert len(calls) == 1
