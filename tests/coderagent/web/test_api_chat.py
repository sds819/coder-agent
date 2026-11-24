"""A turn that runs in the browser: the items, the tool output and the cost."""

import sys

import pytest

pytest.importorskip("fastapi")

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


def test_a_command_cannot_carry_an_image(make_client, wait_for):
    """A command runs on the session, not on a message."""
    client = make_client(responses=[assistant("all done")])
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/messages", json={"text": "/help", "images": [PNG]})
    items = wait_for(client, session_id, "error")

    assert "command" in [item for item in items if item["kind"] == "error"][0]["error"]


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
