import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from typer.testing import CliRunner

from coderagent.config.loader import load_config
from coderagent.core.session import SessionStore
from coderagent.paths import config_home
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.ui.cli import app, main_impl


def _config(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    return load_config([], cwd=tmp_path)


def test_json_output_contains_session_and_messages(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel([{"role": "assistant", "content": "hello", "tool_calls": [], "extra": {"cost": 0.1}}])
    output = main_impl("hi", config, tmp_path, "json", model=model, store=SessionStore(tmp_path))
    payload = json.loads(output)
    assert payload["messages"][0] == {"role": "user", "content": "hi"}
    assert payload["messages"][1]["content"] == "hello"
    assert payload["cost"] == 0.1
    assert payload["stop_reason"] == "end_turn"
    assert payload["error"] == ""
    assert payload["session_id"]


def test_the_session_cost_is_the_whole_session(tmp_path, monkeypatch):
    """The cost of the session is the cost of the turn and of the reflection."""
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel(
        [
            {"role": "assistant", "content": "hello", "tool_calls": [], "extra": {"cost": 0.1}},
            {
                "role": "assistant",
                "content": '{"project_facts": [], "user_preferences": []}',
                "extra": {"cost": 0.05},
            },
        ]
    )
    payload = json.loads(main_impl("hi", config, tmp_path, "json", model=model, store=SessionStore(tmp_path)))
    assert payload["cost"] == 0.1
    assert payload["session_cost"] == pytest.approx(0.15)


def test_the_session_cost_is_in_the_text_output(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel([{"role": "assistant", "content": "hello", "tool_calls": [], "extra": {"cost": 0.1}}])
    output = main_impl("hi", config, tmp_path, "text", model=model, store=SessionStore(tmp_path))
    assert "session_cost=0.1000" in output


def test_error_is_visible_in_the_output(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel([])
    output = main_impl("hi", config, tmp_path, "text", model=model, store=SessionStore(tmp_path))
    assert "[error]" in output
    assert "ran out of responses" in output


def test_text_output_shows_the_assistant_message(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel([{"role": "assistant", "content": "hello", "tool_calls": [], "extra": {"cost": 0.0}}])
    output = main_impl("hi", config, tmp_path, "text", model=model, store=SessionStore(tmp_path))
    assert "hello" in output
    assert "stop_reason=end_turn" in output


def _help() -> str:
    """The help of the app, as the text of it.

    The terminal is made wide and tall on purpose: the options are wrapped
    and cut away when it is small, and the colors break the names apart.
    """
    result = CliRunner().invoke(app, ["--help"], env={"COLUMNS": "200", "LINES": "100"})
    assert result.exit_code == 0
    return re.sub(r"\x1b\[[0-9;]*m", "", result.output)


def test_help_is_available():
    help_text = _help()
    assert "--output-format" in help_text
    assert "--profile" in help_text
    assert "--output-schema" in help_text


def _model(*arguments: str, tmp_path=None) -> "CliRunner":
    """The command of the model, with the environment of the user out of the way."""
    return CliRunner().invoke(app, ["model", *arguments, "--cwd", str(tmp_path or ".")])


def test_the_model_command_shows_the_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("MSWEA_MODEL_NAME", raising=False)

    result = _model(tmp_path=tmp_path)

    assert result.exit_code == 0
    assert "model:" in result.output
    assert "provider:" in result.output
    assert "api key:" in result.output
    assert str(config_home() / "config.yaml") in result.output


def test_the_model_command_writes_the_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("MSWEA_MODEL_NAME", raising=False)

    result = _model("--name", "deepseek/deepseek-flash", tmp_path=tmp_path)

    assert result.exit_code == 0
    assert "deepseek/deepseek-flash" in (config_home() / "config.yaml").read_text(encoding="utf-8")


def test_the_try_out_fails_and_writes_nothing(tmp_path, monkeypatch):
    """The try-out and the writing are two steps: the try-out writes nothing."""
    monkeypatch.delenv("MSWEA_MODEL_NAME", raising=False)

    result = _model("--test", "--name", "not-a-real-provider/nope", tmp_path=tmp_path)

    assert result.exit_code == 1
    assert "error" in result.output
    assert not (config_home() / "config.yaml").exists()


def test_the_answer_fits_the_schema(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel(
        [{"role": "assistant", "content": '{"answer": "hi"}', "tool_calls": [], "extra": {"cost": 0.0}}]
    )
    payload = json.loads(
        main_impl(
            "hi",
            config,
            tmp_path,
            "json",
            model=model,
            store=SessionStore(tmp_path),
            output_schema={"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
        )
    )
    assert payload["output"] == {"answer": "hi"}
    assert payload["stop_reason"] == "end_turn"


def test_a_schema_file_that_is_not_json_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    schema = tmp_path / "schema.json"
    schema.write_text("not json", encoding="utf-8")
    result = CliRunner().invoke(app, ["--task", "hi", "--output-schema", str(schema), "--cwd", str(tmp_path)])
    assert result.exit_code != 0
    assert "not valid JSON" in result.output


def test_a_schema_file_that_cannot_be_read_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(
        app, ["--task", "hi", "--output-schema", str(tmp_path / "nope.json"), "--cwd", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "cannot be read" in result.output


def test_a_profile_that_does_not_exist_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(app, ["--profile", "nope", "--cwd", str(tmp_path)])
    assert result.exit_code == 1
    assert "unknown profile" in str(result.exception)


def test_a_configuration_that_is_not_understood_is_reported(tmp_path, monkeypatch):
    """A mistake in the configuration is said in words, not in a traceback."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(app, ["--task", "hi", "-c", "permissions.mode=dffault", "--cwd", str(tmp_path)])
    assert result.exit_code != 0
    assert "not understood" in result.output
    assert "unknown permission mode 'dffault'" in result.output


def test_the_sessions_of_the_directory_are_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    result = CliRunner().invoke(app, ["--list", "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    assert session.id in result.output


def test_a_session_can_be_resumed(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    result = CliRunner().invoke(app, ["--resume", session.id, "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    assert session.id in result.output


def test_a_slash_command_runs_instead_of_a_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(app, ["--task", "/help", "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    assert "/compact" in result.output


def test_an_unknown_command_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(app, ["--task", "/nope", "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    assert "Unknown command" in result.output


def test_the_trace_of_a_session_is_exported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    result = CliRunner().invoke(app, ["export", "--session", session.id, "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["trajectory_format"] == "coder-agent-1.0"
    assert payload["session"]["id"] == session.id
    assert payload["events"]


def test_the_trace_is_written_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    target = tmp_path / "trace.json"
    result = CliRunner().invoke(
        app, ["export", "--session", session.id, "--format", "json", "--out", str(target), "--cwd", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert json.loads(target.read_text(encoding="utf-8"))["session"]["id"] == session.id


def test_the_trace_is_exported_as_otel(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    result = CliRunner().invoke(app, ["export", "--session", session.id, "--format", "otel", "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    assert "resourceSpans" in json.loads(result.output)


def test_an_unknown_format_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    result = CliRunner().invoke(app, ["export", "--session", session.id, "--format", "xml", "--cwd", str(tmp_path)])
    assert result.exit_code == 0
    assert "Unknown format" in result.output


def test_the_trace_is_pushed_to_the_backend(tmp_path, monkeypatch):
    """`coder export --push` sends the trace to the address of the configuration."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    home = tmp_path / "home"
    home.mkdir()
    store = SessionStore(home / "sessions")
    session = store.create(tmp_path)

    received = []

    class Backend(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", 0))
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            """The test does not want the noise of the server."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1/traces"
    (home / "config.yaml").write_text(json.dumps({"telemetry": {"otel_endpoint": endpoint}}), encoding="utf-8")
    try:
        result = CliRunner().invoke(
            app, ["export", "--session", session.id, "--format", "otel", "--push", "--cwd", str(tmp_path)]
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.exit_code == 0
    assert "Pushed the trace" in result.output
    assert received[0]["resourceSpans"][0]["scopeSpans"][0]["scope"]["name"] == "coderagent"


def test_pushing_without_an_address_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    store = SessionStore(tmp_path / "home" / "sessions")
    session = store.create(tmp_path)
    result = CliRunner().invoke(
        app, ["export", "--session", session.id, "--format", "otel", "--push", "--cwd", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "No telemetry.otel_endpoint" in result.output


def test_the_last_answer_is_written_to_a_file(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel(
        [{"role": "assistant", "content": "the work is done", "tool_calls": [], "extra": {"cost": 0.0}}]
    )
    target = tmp_path / "answer.txt"
    main_impl("hi", config, tmp_path, "text", model=model, store=SessionStore(tmp_path), output_last_message=target)
    assert target.read_text(encoding="utf-8") == "the work is done"


def test_the_history_is_not_written_when_it_is_not_saved(tmp_path, monkeypatch):
    """`history.persistence: save-none` keeps the session in the memory."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    config = load_config(["history.persistence=save-none"], cwd=tmp_path)
    model = ScriptedModel([{"role": "assistant", "content": "hello", "tool_calls": [], "extra": {"cost": 0.0}}])
    main_impl("hi", config, tmp_path, "text", model=model)
    assert list((tmp_path / "home" / "sessions").glob("*")) == []


def test_the_history_is_written_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    config = load_config([], cwd=tmp_path)
    model = ScriptedModel([{"role": "assistant", "content": "hello", "tool_calls": [], "extra": {"cost": 0.0}}])
    main_impl("hi", config, tmp_path, "text", model=model)
    assert list((tmp_path / "home" / "sessions").glob("*.jsonl"))


def test_the_option_is_in_the_help():
    assert "--output-last-message" in _help()


def test_the_program_of_the_user_is_told_that_the_turn_is_over(tmp_path, monkeypatch):
    """The notifier of the command line gets the answer of the agent."""
    config = _config(tmp_path, monkeypatch)
    seen = tmp_path / "seen.txt"
    script = tmp_path / "notifier.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(sys.argv[2] + '|' + sys.argv[3], encoding='utf-8')\n",
        encoding="utf-8",
    )
    config.ui.notify_command = f"{sys.executable} {script} {seen}"
    model = ScriptedModel(
        [{"role": "assistant", "content": "the work is done", "tool_calls": [], "extra": {"cost": 0.0}}]
    )
    main_impl("hi", config, tmp_path, "text", model=model, store=SessionStore(tmp_path))
    assert seen.read_text(encoding="utf-8") == "coder|the work is done"


def test_without_a_notifier_nothing_is_run(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    model = ScriptedModel(
        [{"role": "assistant", "content": "the work is done", "tool_calls": [], "extra": {"cost": 0.0}}]
    )
    assert main_impl("hi", config, tmp_path, "text", model=model, store=SessionStore(tmp_path))


def test_the_start_does_not_wait_for_litellm():
    """litellm takes two seconds to import and fetches a price table from the network.

    Neither may happen before the agent calls a model.
    """
    code = (
        "import os, sys\n"
        "import coderagent.ui.cli\n"
        "print('litellm' in sys.modules, os.environ.get('LITELLM_LOCAL_MODEL_COST_MAP'))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "False true"
