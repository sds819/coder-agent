"""A turn that runs in the browser: the items, the tool output and the cost."""

import json
import sys
import threading
import time

import pytest
import yaml

pytest.importorskip("fastapi")

from coderagent.paths import config_home  # noqa: E402
from coderagent.testing.scripted_model import ScriptedModel  # noqa: E402
from tests.coderagent.web.conftest import assistant, bash_call, read_call, trust  # noqa: E402

PNG = "data:image/png;base64,iVBORw0KGgo="
"""An image of one pixel, as the browser sends it."""


def test_a_turn_shows_the_conversation_and_the_tool(make_client, send, wait_for):
    client = make_client(
        responses=[
            assistant(tool_calls=[bash_call("echo hello")]),
            assistant("all done", cost=0.5),
        ],
        permission_mode="bypass",
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")
    kinds = [item["kind"] for item in items]

    assert kinds.index("user_message") < kinds.index("tool_call")
    assert kinds[-1] == "turn_end"
    assert [item["content"] for item in items if item["kind"] == "user_message"] == ["say hello"]
    assert [item["content"] for item in items if item["kind"] == "assistant_message"] == ["", "all done"]


def test_the_tool_card_knows_which_tool_was_called(make_client, send, wait_for):
    client = make_client(
        responses=[assistant(tool_calls=[bash_call("echo hello")]), assistant("done")],
        permission_mode="bypass",
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")
    call = [item for item in items if item["kind"] == "tool_call"][0]

    assert call["tool"] == "bash"
    assert call["args"] == {"command": "echo hello"}
    assert call["tool_call_id"] == "call_1"
    assert "echo hello" in call["summary"]


def test_the_output_of_the_tool_is_in_the_items(make_client, send, wait_for):
    client = make_client(
        responses=[assistant(tool_calls=[bash_call("echo hello")]), assistant("done")],
        permission_mode="bypass",
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")
    results = [item for item in items if item["kind"] == "tool_result"]

    assert "hello" in results[0]["content"]
    assert results[0]["is_error"] is False
    assert results[0]["tool_call_id"] == "call_1"


def test_the_turn_reports_what_it_cost(make_client, send, wait_for):
    client = make_client(
        responses=[assistant(tool_calls=[bash_call("echo hello")]), assistant("done", cost=0.5)],
        permission_mode="bypass",
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")
    end = items[-1]

    assert end["kind"] == "turn_end"
    assert end["stop_reason"] == "end_turn"
    assert end["cost"] == pytest.approx(0.5)
    assert end["session_cost"] == pytest.approx(0.5)


def test_a_rewritten_prompt_keeps_what_the_user_typed(make_client, send, wait_for, tmp_path):
    """The browser shows the prompt of the model, and what the user wrote."""
    script = tmp_path / "rewrite.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "print(json.dumps({'updatedInput': data['prompt'] + ' (rewritten)'}))\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} {script}"
    trust(tmp_path, command)
    client = make_client(
        responses=[assistant("all done")],
        project_config=(
            "hooks:\n"
            "  events:\n"
            "    UserPromptSubmit:\n"
            "      - hooks:\n"
            "          - type: command\n"
            f'            command: "{command}"\n'
        ),
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")
    message = [item for item in items if item["kind"] == "user_message"][0]

    assert message["content"] == "say hello (rewritten)"
    assert message["original"] == "say hello"


def test_a_hook_of_the_project_that_is_not_trusted_does_not_run(make_client, send, wait_for, tmp_path):
    """The hook of the project runs code: it waits for a decision of the user."""
    script = tmp_path / "rewrite.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "print(json.dumps({'updatedInput': data['prompt'] + ' (rewritten)'}))\n",
        encoding="utf-8",
    )
    client = make_client(
        responses=[assistant("all done")],
        project_config=(
            "hooks:\n"
            "  events:\n"
            "    UserPromptSubmit:\n"
            "      - hooks:\n"
            "          - type: command\n"
            f'            command: "{sys.executable} {script}"\n'
        ),
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")
    message = [item for item in items if item["kind"] == "user_message"][0]

    assert message["content"] == "say hello"


def test_an_empty_message_is_refused(make_client):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]

    assert client.post(f"/api/sessions/{session_id}/messages", json={"text": "   "}).status_code == 400


def test_a_message_with_an_image_reaches_the_model(make_client, wait_for):
    """The image goes to the model with the text, not as a file on the disk."""
    model = ScriptedModel([assistant("all done")])
    client = make_client(model=model)
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/messages", json={"text": "what is this?", "images": [PNG]})
    items = wait_for(client, session_id, "turn_end")

    content = model.calls[0][-1]["content"]
    assert content[0] == {"type": "text", "text": "what is this?"}
    assert content[1] == {"type": "image_url", "image_url": {"url": PNG}}
    message = [item for item in items if item["kind"] == "user_message"][0]
    assert message["text"] == "what is this?"
    assert message["images"] == [PNG]


def test_a_message_with_only_an_image_is_sent(make_client, wait_for):
    model = ScriptedModel([assistant("all done")])
    client = make_client(model=model)
    session_id = client.post("/api/sessions").json()["id"]

    response = client.post(f"/api/sessions/{session_id}/messages", json={"text": "", "images": [PNG]})
    items = wait_for(client, session_id, "turn_end")

    assert response.status_code == 202
    assert {"type": "image_url", "image_url": {"url": PNG}} in model.calls[0][-1]["content"]
    assert [item for item in items if item["kind"] == "user_message"][0]["images"] == [PNG]


def test_an_image_that_is_not_an_image_is_refused(make_client):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]

    response = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "look", "images": ["data:text/plain;base64,aGk="]}
    )

    assert response.status_code == 400
    assert "not a type" in response.json()["detail"]


def test_an_image_that_is_too_big_is_refused(make_client):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]

    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "look", "images": ["data:image/png;base64," + "A" * (7 * 1024 * 1024)]},
    )

    assert response.status_code == 400
    assert "too big" in response.json()["detail"]


def test_an_image_that_is_not_base64_is_refused(make_client):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]

    response = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "look", "images": ["data:image/png,raw"]}
    )

    assert response.status_code == 400
    assert "base64" in response.json()["detail"]


def test_a_command_cannot_carry_an_image(make_client, wait_for):
    """A command runs on the session, not on a message."""
    client = make_client(responses=[assistant("all done")])
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/messages", json={"text": "/help", "images": [PNG]})
    items = wait_for(client, session_id, "error")

    assert "command" in [item for item in items if item["kind"] == "error"][0]["error"]
    assert any(item["kind"] == "turn_end" for item in items)


def test_a_model_that_cannot_see_the_picture_refuses_the_turn(make_client, wait_for):
    """The model would answer about the picture anyway, and the answer would be made up."""
    model = ScriptedModel([assistant("all done")])
    client = make_client(model=model, capabilities={"scripted": {"image": False}})
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/messages", json={"text": "what is this?", "images": [PNG]})
    items = wait_for(client, session_id, "error")

    assert not model.calls
    assert "cannot take pictures" in [item for item in items if item["kind"] == "error"][0]["error"]


def test_a_model_nobody_knows_about_is_asked_first(make_client, wait_for):
    """Nobody said what the model takes, so the agent asks it, and remembers."""
    model = ScriptedModel([assistant("magenta"), assistant("all done")])
    client = make_client(model=model, capabilities={})
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/messages", json={"text": "what is this?", "images": [PNG]})
    items = wait_for(client, session_id, "turn_end")

    assert items[-1]["stop_reason"] == "end_turn"
    assert len(model.calls) == 2
    written = yaml.safe_load((config_home() / "config.yaml").read_text(encoding="utf-8"))
    assert written["model"]["capabilities"] == {"scripted": {"image": True}}


def test_a_model_that_fails_ends_the_turn_with_an_error(make_client, send, wait_for):
    client = make_client(responses=[])
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_end")

    assert items[-1]["stop_reason"] == "error"
    assert items[-1]["error"]
    assert [item["kind"] for item in items if item["kind"] == "error"]


def test_a_turn_that_was_cut_off_says_why_it_ended(make_client, send, wait_for):
    """A turn that stops at the ceiling of the model calls has to say so."""
    client = make_client(
        responses=[assistant(tool_calls=[read_call("a.txt")])],
        permission_mode="default",
        project_config="agent:\n  max_turns: 1\n",
    )
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "say hello")

    items = wait_for(client, session_id, "turn_stopped")
    stopped = [item for item in items if item["kind"] == "turn_stopped"][0]

    assert stopped["stop_reason"] == "max_turns"
    assert stopped["calls"] == 1
    assert items[-1]["kind"] == "turn_end"
    assert items[-1]["stop_reason"] == "max_turns"


def test_the_stream_ends_when_the_server_stops(make_client):
    """The server waits for its connections before it stops: the stream has to end."""
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]
    runtime = client.app.state.registry.get(session_id)

    def stop():
        time.sleep(0.5)
        runtime.end_streams()

    stopper = threading.Thread(target=stop)
    stopper.start()
    with client.stream("GET", f"/api/sessions/{session_id}/stream") as response:
        body = "".join(response.iter_text())
    stopper.join()

    kinds = [json.loads(line[6:])["kind"] for line in body.splitlines() if line.startswith("data: ")]

    assert "stream_end" not in kinds
    assert ": keep-alive" not in body
    assert response.status_code == 200


def test_the_browser_is_told_when_the_agent_thinks(make_client, send, wait_for):
    """The dots of the browser show while the agent thinks."""
    client = make_client(responses=[assistant("hi", cost=0.1)], permission_mode="bypass")
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "hello")

    items = wait_for(client, session_id, "turn_end")

    states = [item["state"] for item in items if item["kind"] == "state"]
    assert "thinking" in states
    assert states[-1] == "done"


def test_the_page_has_the_dots_of_the_terminal(make_client):
    """The browser shows the same animation as the terminal."""
    page = make_client().get("/").text

    assert 'window.DOT_FRAMES = [".", "..", "...", ".."]' in page
