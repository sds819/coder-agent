"""The tests of the web interface. They never touch the data of the user."""

import time

import pytest
import yaml

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from coderagent.config.loader import load_config  # noqa: E402
from coderagent.core.session import SessionStore  # noqa: E402
from coderagent.testing.scripted_model import ScriptedModel  # noqa: E402
from coderagent.web.app import create_app  # noqa: E402

BASE_CONFIG = "memory:\n  enabled: false\n"
"""The reflection of the end of a turn is off, so that the scripted model is not used up."""


@pytest.fixture
def make_client(tmp_path):
    """A web interface with a scripted model behind it."""
    clients = []

    def build(responses=None, model=None, project_config="", capabilities=None, **kwargs):
        project = tmp_path / ".coderagent"
        project.mkdir(exist_ok=True)
        (project / "config.yaml").write_text(BASE_CONFIG + project_config, encoding="utf-8")
        takes = {"scripted": {"image": True}} if capabilities is None else capabilities
        spec = tmp_path / "capabilities.yaml"
        spec.write_text(yaml.safe_dump({"model": {"capabilities": takes}}), encoding="utf-8")
        """The scripted model looks at pictures. A project may not say what the
        model of the user takes, so the tests say it here: in a spec, because a
        session reads the files again and would lose anything said in memory."""
        config = load_config([], cwd=tmp_path)
        app = create_app(
            config,
            tmp_path,
            store=SessionStore(tmp_path / "sessions"),
            model=model or ScriptedModel(responses or []),
            config_spec=[str(spec)],
            **kwargs,
        )
        client = TestClient(app, headers={"X-Coder-Client": "1"})
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.close()


@pytest.fixture
def wait_for():
    """Wait until an item of a kind arrives."""

    def wait(client, session_id, kind, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            items = client.get(f"/api/sessions/{session_id}/items").json()["items"]
            if any(item["kind"] == kind for item in items):
                return items
            time.sleep(0.05)
        raise AssertionError(f"no {kind} item arrived")

    return wait


@pytest.fixture
def send():
    """Hand a message to a session."""

    def run(client, session_id, text="hello"):
        response = client.post(f"/api/sessions/{session_id}/messages", json={"text": text})
        assert response.status_code == 202
        return response

    return run


def bash_call(command: str, call_id: str = "call_1") -> dict:
    import json

    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "bash", "arguments": json.dumps({"command": command})},
    }


def read_call(path: str, call_id: str = "call_1") -> dict:
    import json

    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "read", "arguments": json.dumps({"path": path})},
    }


def trust(project, command: str) -> None:
    """Trust a hook of the project, so that it is used."""
    from coderagent.core.trust import TRUSTED, key_of, remember

    remember(project, key_of("hook", command), TRUSTED, command)


def assistant(content: str = "", tool_calls=None, cost: float = 0.0) -> dict:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls or [],
        "extra": {"cost": cost},
    }
