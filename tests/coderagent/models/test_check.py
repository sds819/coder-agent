"""The try-out of the model: what it says when the model does not answer."""

from coderagent.models import check
from coderagent.testing.scripted_model import ScriptedModel


def _effective(name: str = "not-a-real-provider/nope") -> dict:
    return {"model_name": name, "model_kwargs": {}, "requested": name}


def test_a_model_that_is_not_there_is_reported():
    report = check.test_connection(_effective())

    assert report["ok"] is False
    assert report["error"]
    """The model does not exist, so there is no answer: the report says why."""


def test_the_report_says_the_error():
    text = check.report_text({"resolved": {"model_name": "x/y"}, "error": "AuthenticationError: no key"})

    assert "model: x/y" in text
    assert "error: AuthenticationError: no key" in text


def test_the_report_says_the_tools_and_the_latency():
    text = check.report_text(
        {
            "resolved": {"model_name": "x/y", "provider": "openai"},
            "latency_ms": 123,
            "cost": 0.5,
            "tools": {"ok": True},
        }
    )

    assert "latency: 123 ms" in text
    assert "the model calls the tools" in text


def test_the_report_says_the_tools_that_do_not_work():
    text = check.report_text(
        {
            "resolved": {"model_name": "x/y"},
            "tools": {"ok": False, "error": "the model did not call the tool"},
        }
    )

    assert "the model did not call the tool" in text


def test_the_model_has_to_call_the_tools():
    call = {"id": "c1", "type": "function", "function": {"name": "ping", "arguments": "{}"}}

    assert check.check_tools(ScriptedModel([{"role": "assistant", "content": "", "tool_calls": [call]}]))["ok"] is True
    assert check.check_tools(ScriptedModel([{"role": "assistant", "content": "no tool"}]))["error"] == (
        "the model did not call the tool"
    )


def test_a_backend_that_raises_is_reported():
    class Broken:
        def query(self, messages, tools=None, **kwargs):
            raise RuntimeError("no connection")

    assert check.check_tools(Broken())["error"] == "RuntimeError: no connection"


def test_the_file_of_the_aliases_is_reported():
    assert check.check_litellm_config("")["ok"] is True
    assert check.check_litellm_config("/nope/there.yaml")["error"] == "the file does not exist"
