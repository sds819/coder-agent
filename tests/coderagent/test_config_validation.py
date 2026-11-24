"""The configuration that is wrong is told to the user, not taken silently."""

import pytest
from pydantic import ValidationError

from coderagent.config.loader import load_config
from coderagent.config.schema import Config
from coderagent.tools.permissions import PermissionPolicy


def _user_config(tmp_path, monkeypatch, text: str) -> None:
    """The configuration of the user."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    (home / "config.yaml").write_text(text, encoding="utf-8")


def _project_config(tmp_path, text: str) -> None:
    """The configuration of the project."""
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "text",
    [
        "permissions:\n  mode: dffault\n",
        "permissions:\n  network: closed\n",
        "sandbox:\n  type: loca\n",
        "tools:\n  enabled:\n    - reed\n",
        "tools:\n  disabled:\n    - reed\n",
        "hooks:\n  events:\n    PreToolUsee: []\n",
        "model:\n  routing:\n    chep: cheap/model\n",
        "model:\n  routing_rules:\n    - when: calls > 5\n      purpose: chep\n",
        "model:\n  routing_rules:\n    - when: calls >\n      purpose: cheap\n",
        "permissons:\n  mode: readonly\n",
        "agent:\n  max_turns: -1\n",
        "agent:\n  cost_limit: -0.5\n",
        "tools:\n  bash_timeout: -1\n",
        "context:\n  compact_threshold: 1.5\n",
        "context:\n  context_window: 0\n",
    ],
)
def test_a_mistake_of_the_user_is_refused(tmp_path, monkeypatch, text):
    """A setting that means nothing is a mistake the user has to hear about."""
    _user_config(tmp_path, monkeypatch, text)
    with pytest.raises(ValidationError):
        load_config([], cwd=tmp_path)


def test_the_mistake_says_what_is_wrong(tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch, "permissions:\n  mode: dffault\n")
    with pytest.raises(ValidationError, match="unknown permission mode 'dffault'"):
        load_config([], cwd=tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        "permissons:\n  mode: readonly\n",
        "tools:\n  enabled:\n    - reed\n",
        "hooks:\n  events:\n    PreToolUsee: []\n",
        "agent:\n  max_turns: -1\n",
    ],
)
def test_a_mistake_of_the_project_is_dropped(tmp_path, monkeypatch, text):
    """A project may not break the session of the user: what it says wrong is left out."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    _project_config(tmp_path, text)
    config = load_config([], cwd=tmp_path)
    assert config.agent.max_turns == 100
    assert config.tools.enabled
    assert config.permissions.mode == "default"


def test_the_tools_of_the_project_that_are_wrong_are_not_taken_away(tmp_path, monkeypatch):
    """A project that names a tool that does not exist does not empty the tool set."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    _project_config(tmp_path, "tools:\n  enabled:\n    - reed\n")
    assert "read" in load_config([], cwd=tmp_path).tools.enabled


def test_the_dead_field_of_the_working_directory_is_gone():
    """`cwd` was in the configuration and nothing read it."""
    assert not hasattr(Config(), "cwd")


def test_the_directories_are_relative_to_the_working_directory_of_the_session(tmp_path):
    """The directory of the session is the ground a relative path stands on."""
    policy = PermissionPolicy(cwd=tmp_path, include_dirs=["extra"])
    assert policy.include_dirs == [(tmp_path / "extra").resolve()]


def test_a_relative_directory_is_not_relative_to_the_process(tmp_path, monkeypatch):
    """The process may be in another directory: the session is what counts."""
    monkeypatch.chdir(tmp_path.parent)
    policy = PermissionPolicy(cwd=tmp_path / "project", include_dirs=["extra"])
    assert policy.include_dirs == [((tmp_path / "project") / "extra").resolve()]
