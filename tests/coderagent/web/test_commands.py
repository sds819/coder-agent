"""The slash commands of the web interface."""

import subprocess
import time

import pytest

from coderagent.testing.scripted_model import ScriptedModel

pytest.importorskip("fastapi")


def test_a_command_answers_in_the_stream(make_client, send, wait_for):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "/help")

    items = wait_for(client, session_id, "command_output")
    output = [item["text"] for item in items if item["kind"] == "command_output"]

    assert output
    assert any("help" in text.lower() for text in output)


def test_the_command_that_ran_is_announced(make_client, send, wait_for):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "/help")

    items = wait_for(client, session_id, "command_end")

    assert items[-1]["kind"] == "command_end"


def test_the_commands_are_listed(make_client):
    client = make_client()

    names = [command["name"] for command in client.get("/api/commands").json()["commands"]]

    assert {"help", "model", "mode", "resume", "fork", "clear"} <= set(names)


def test_the_commands_say_what_they_take(make_client):
    """The interface of the browser shows the options of a command."""
    client = make_client()

    commands = {command["name"]: command for command in client.get("/api/commands").json()["commands"]}

    assert "acceptEdits" in commands["mode"]["usage"]
    assert commands["status"]["usage"] == ""


def test_an_unknown_command_says_so(make_client, send, wait_for):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "/nosuchcommand")

    items = wait_for(client, session_id, "command_output")

    assert "Unknown command" in [item["text"] for item in items if item["kind"] == "command_output"][0]


def test_the_exit_command_says_the_server_keeps_running(make_client, send, wait_for):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "/exit")

    items = wait_for(client, session_id, "command_output")

    assert "ctrl+c" in [item["text"] for item in items if item["kind"] == "command_output"][0]


def test_the_review_command_gives_the_diff_to_the_model(make_client, send, wait_for, tmp_path):
    """The review is a turn of the session: the diff goes into the prompt."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("print('b')\n", encoding="utf-8")
    model = ScriptedModel([{"role": "assistant", "content": "one thing is wrong"}])
    client = make_client(model=model)
    session_id = client.post("/api/sessions").json()["id"]

    send(client, session_id, "/review")
    wait_for(client, session_id, "turn_end")

    assert "+print('b')" in str(model.calls[0])


def test_clear_starts_a_new_session_and_the_registry_follows(make_client, send):
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]
    send(client, session_id, "/clear")

    deadline = time.time() + 15
    while time.time() < deadline:
        sessions = client.get("/api/sessions").json()["sessions"]
        if sessions and sessions[0]["id"] != session_id:
            break
        time.sleep(0.05)
    new_id = sessions[0]["id"]

    assert new_id != session_id
    items = client.get(f"/api/sessions/{new_id}/items").json()["items"]
    switched = [item for item in items if item["kind"] == "session_switched"][0]
    assert switched["session_id"] == new_id
    assert switched["previous_session_id"] == session_id
    assert client.get(f"/api/sessions/{new_id}").status_code == 200
    """The old session is still in the log, it is just not the one that is running."""
