"""The environment that the commands of the agent see."""

import pytest

from coderagent.config.schema import Config
from coderagent.core.shell_env import CORE, build


def test_the_keys_of_the_user_stay_out_of_the_shell():
    env = build("all", [], [], {}, {"PATH": "/bin", "OPENAI_API_KEY": "secret", "HOME": "/home/me"})
    assert "OPENAI_API_KEY" not in env
    assert env["PATH"] == "/bin"


def test_the_environment_of_the_user_is_inherited():
    env = build("all", [], [], {}, {"PATH": "/bin", "MY_PROJECT": "yes"})
    assert env["MY_PROJECT"] == "yes"


def test_core_keeps_only_what_a_command_needs():
    env = build("core", [], [], {}, {"PATH": "/bin", "HOME": "/home/me", "MY_PROJECT": "yes"})
    assert set(env) == {"PATH", "HOME"}
    assert set(env) <= set(CORE)


def test_none_leaves_nothing_but_what_the_user_sets():
    env = build("none", [], [], {"CI": "1"}, {"PATH": "/bin", "HOME": "/home/me"})
    assert env == {"CI": "1"}


def test_a_pattern_of_the_user_hides_more():
    env = build("all", ["MY_*"], [], {}, {"PATH": "/bin", "MY_TOKEN": "x", "OTHER": "y"})
    assert "MY_TOKEN" not in env
    assert env["OTHER"] == "y"


def test_the_user_may_open_a_secret_again():
    env = build("all", [], ["OPENAI_API_KEY"], {}, {"OPENAI_API_KEY": "secret"})
    assert env["OPENAI_API_KEY"] == "secret"


def test_the_variables_of_the_user_always_win():
    env = build("all", [], [], {"CI": "1"}, {"PATH": "/bin"})
    assert env["CI"] == "1"


def test_an_inheritance_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="unknown inheritance"):
        Config(shell_environment={"inherit": "some"})


def test_a_project_may_not_show_what_the_user_hid(tmp_path):
    """The project may hide more of the environment, never open it."""
    from coderagent.core.trust import tightened

    project = {"shell_environment": {"include": ["*_API_KEY"], "exclude": ["MY_*"]}}
    result = tightened(project)
    assert "include" not in result["shell_environment"]
    assert result["shell_environment"]["exclude"] == ["MY_*"]


def test_the_excludes_of_every_layer_are_added_up(tmp_path):
    """The project hides more, the user hides more, and both hold."""
    from coderagent.config.loader import load_config

    (tmp_path / ".coderagent").mkdir()
    (tmp_path / ".coderagent" / "config.yaml").write_text(
        "shell_environment:\n  exclude: ['PROJECT_*']\n", encoding="utf-8"
    )
    config = load_config(cwd=tmp_path)
    assert "PROJECT_*" in config.shell_environment.exclude


def test_the_commands_of_the_agent_do_not_see_the_keys(tmp_path, monkeypatch):
    """The key of the provider is in the process of the agent, not in its shell."""
    from coderagent.run import build_loop
    from coderagent.tools.builtin.shell import BashTool

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    loop = build_loop(Config(), tmp_path)
    result = BashTool().run({"command": "echo [$OPENAI_API_KEY]"}, loop.executor.ctx_factory())
    assert result.content.strip() == "[]"


def test_the_commands_of_the_agent_see_what_the_user_sets(tmp_path):
    from coderagent.run import build_loop
    from coderagent.tools.builtin.shell import BashTool

    config = Config(shell_environment={"set": {"MY_FLAG": "on"}})
    loop = build_loop(config, tmp_path)
    result = BashTool().run({"command": "echo $MY_FLAG"}, loop.executor.ctx_factory())
    assert result.content.strip() == "on"
