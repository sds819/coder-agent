"""The files a user mentions: `@path` in a prompt and `/mention <path>`."""

from coderagent.core.events import EventBus
from coderagent.core.loop import AgentLoop
from coderagent.core.mentions import expand
from coderagent.core.session import SessionStore
from coderagent.models.gateway import ModelGateway
from coderagent.testing.factory import build_context, build_executor
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.tools.permissions import PermissionPolicy, Rule


def _policy(cwd, rules=None) -> PermissionPolicy:
    return PermissionPolicy("default", rules or [], cwd=cwd)


def test_the_content_of_a_mentioned_file_goes_into_the_message(tmp_path):
    (tmp_path / "a.py").write_text("print('hi')\n", encoding="utf-8")
    text = expand("look at @a.py please", tmp_path, _policy(tmp_path))
    assert "print('hi')" in text
    assert '<file path="a.py">' in text


def test_a_name_that_is_not_a_file_stays_as_it_is(tmp_path):
    assert expand("write to me@example.com", tmp_path, _policy(tmp_path)) == "write to me@example.com"


def test_a_decorator_stays_as_it_is(tmp_path):
    assert expand("@property", tmp_path, _policy(tmp_path)) == "@property"


def test_the_punctuation_after_the_path_stays(tmp_path):
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    assert expand("look at @a.py, please", tmp_path, _policy(tmp_path)).endswith("</file>, please")


def test_a_file_that_is_not_text_is_not_put_in(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"\x00\x01\x02")
    text = expand("look at @a.bin", tmp_path, _policy(tmp_path))
    assert "This file is not text." in text


def test_a_long_file_is_cut(tmp_path):
    (tmp_path / "a.txt").write_text("x" * 30000, encoding="utf-8")
    text = expand("look at @a.txt", tmp_path, _policy(tmp_path))
    assert "the rest of the file is not here" in text


def test_a_file_outside_the_working_directory_is_not_put_in(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    text = expand(f"look at @{outside}", tmp_path, _policy(tmp_path))
    assert "secret" not in text
    assert "The agent may not read this file." in text


def test_a_file_that_is_denied_is_not_put_in(tmp_path):
    (tmp_path / "secret.txt").write_text("secret\n", encoding="utf-8")
    policy = _policy(tmp_path, [Rule(tool="*", pattern="secret.txt", decision="deny")])
    text = expand("look at @secret.txt", tmp_path, policy)
    assert "secret\n" not in text
    assert "The agent may not read this file." in text


def test_a_file_that_mentions_another_file_does_not_pull_it_in(tmp_path):
    (tmp_path / "a.py").write_text("see @b.py\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("the other file\n", encoding="utf-8")
    text = expand("look at @a.py", tmp_path, _policy(tmp_path))
    assert "the other file" not in text


def test_a_secret_in_a_mentioned_file_is_redacted(tmp_path):
    """The content of the file goes into the log of the session, so the secrets go."""
    (tmp_path / "a.py").write_text("key = 'sk-abcdefghijklmnopqrstuvwxyz'\n", encoding="utf-8")
    text = expand("look at @a.py", tmp_path, _policy(tmp_path))
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in text
    assert "[redacted]" in text


def _loop(tmp_path, responses):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    bus = EventBus()
    executor = build_executor(tmp_path, store=store, context=build_context(tmp_path, session=session, bus=bus))
    return AgentLoop(
        ModelGateway(ScriptedModel(responses)),
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
    )


def test_the_model_sees_the_content_of_the_file(tmp_path):
    (tmp_path / "a.py").write_text("print('hi')\n", encoding="utf-8")
    loop = _loop(tmp_path, [{"role": "assistant", "content": "ok", "tool_calls": [], "extra": {"cost": 0.0}}])
    result = loop.run_turn("look at @a.py")
    assert "print('hi')" in result.messages[0]["content"]
