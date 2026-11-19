"""The review of the changes, from the browser."""

import subprocess

import pytest

from coderagent.testing.scripted_model import ScriptedModel

pytest.importorskip("fastapi")


@pytest.fixture
def project(tmp_path):
    """A project with one change that is not committed yet."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("print('b')\n", encoding="utf-8")
    return tmp_path


def test_the_review_gives_the_diff_to_the_model(make_client, wait_for, project):
    """The button reviews the changes of the project."""
    model = ScriptedModel([{"role": "assistant", "content": "one thing is wrong"}])
    client = make_client(model=model)
    session_id = client.post("/api/sessions").json()["id"]

    answer = client.post(f"/api/sessions/{session_id}/review")

    assert answer.status_code == 202
    assert "+print('b')" in answer.json()["diff"]
    wait_for(client, session_id, "turn_end")
    assert "+print('b')" in str(model.calls[0])


def test_the_diff_is_shown_to_the_browser(make_client, wait_for, project):
    """The browser sees what is being reviewed."""
    client = make_client([{"role": "assistant", "content": "one thing is wrong"}])
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/review")

    items = wait_for(client, session_id, "review")
    review = [item for item in items if item["kind"] == "review"][0]
    assert "+print('b')" in review["diff"]


def test_the_review_answers_in_the_stream(make_client, wait_for, project):
    """The findings of the review come back like any other answer."""
    client = make_client([{"role": "assistant", "content": "one thing is wrong"}])
    session_id = client.post("/api/sessions").json()["id"]

    client.post(f"/api/sessions/{session_id}/review")

    items = wait_for(client, session_id, "assistant_message")
    assert any(item.get("content") == "one thing is wrong" for item in items if item["kind"] == "assistant_message")


def test_a_project_without_changes_has_nothing_to_review(make_client):
    """A directory that is not a repository has nothing to review."""
    client = make_client()
    session_id = client.post("/api/sessions").json()["id"]

    answer = client.post(f"/api/sessions/{session_id}/review")

    assert answer.status_code == 400
    assert "git" in answer.json()["detail"].lower()


def test_the_page_has_a_review_button(make_client):
    """The button is in the page, in both languages."""
    client = make_client()

    assert 'id="review"' in client.get("/").text
    assert 'id="review"' in client.get("/?lang=zh").text
