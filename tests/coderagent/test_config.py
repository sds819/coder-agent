import pytest
from pydantic import ValidationError

from coderagent.config.loader import load_config
from coderagent.config.schema import BUILTIN_TOOL_NAMES, DEFAULT_SYSTEM_PROMPT, Config
from coderagent.tools.builtin import TOOL_NAMES


def test_builtin_tool_names_match_the_config():
    assert set(TOOL_NAMES) <= set(BUILTIN_TOOL_NAMES)
    """The `task` and `skill` tools are outside the static registry: they need the project."""
    assert set(BUILTIN_TOOL_NAMES) - set(TOOL_NAMES) == {"task", "skill"}


def test_defaults_are_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MSWEA_MODEL_NAME", raising=False)
    config = load_config([], cwd=tmp_path)
    assert config.model.model_name == "anthropic/claude-sonnet-4-5"
    assert config.agent.max_turns == 50
    assert config.tools.enabled == BUILTIN_TOOL_NAMES
    assert config.sandbox.type == "local"


def test_model_name_falls_back_to_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MSWEA_MODEL_NAME", "deepseek/deepseek-flash")
    assert load_config([], cwd=tmp_path).model.model_name == "deepseek/deepseek-flash"


def test_config_file_wins_over_env_var(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    monkeypatch.setenv("MSWEA_MODEL_NAME", "deepseek/deepseek-flash")
    (home / "config.yaml").write_text("model:\n  model_name: openai/gpt-5\n", encoding="utf-8")
    assert load_config([], cwd=tmp_path).model.model_name == "openai/gpt-5"


def test_project_config_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True)
    project.write_text("agent:\n  max_turns: 7\n", encoding="utf-8")
    assert load_config([], cwd=tmp_path).agent.max_turns == 7


def test_user_config_overrides_project_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True)
    project.write_text("agent:\n  max_turns: 7\n", encoding="utf-8")
    (home / "config.yaml").write_text("agent:\n  max_turns: 9\n", encoding="utf-8")
    assert load_config([], cwd=tmp_path).agent.max_turns == 9


def test_cli_spec_overrides_everything(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    (home / "config.yaml").write_text("agent:\n  max_turns: 9\n", encoding="utf-8")
    config = load_config(["agent.max_turns=3"], cwd=tmp_path)
    assert config.agent.max_turns == 3
    assert config.agent.cost_limit == 0.0


def test_key_value_spec_can_set_strings(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    config = load_config(["model.model_name=openai/gpt-5"], cwd=tmp_path)
    assert config.model.model_name == "openai/gpt-5"


def test_invalid_value_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    with pytest.raises(ValidationError):
        load_config(["agent.max_turns=not-a-number"], cwd=tmp_path)


def test_config_defaults_are_valid():
    assert Config().tools.bash_timeout == 120


def test_the_default_prompt_is_the_one_of_the_schema_and_names_the_arguments(tmp_path, monkeypatch):
    """The prompt of the file and the one of the schema must not drift apart."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    prompt = load_config([], cwd=tmp_path).agent.system_prompt
    assert prompt == DEFAULT_SYSTEM_PROMPT
    assert "argument names of its schema" in prompt


def test_the_thinking_budget_is_read_from_the_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    assert load_config(["model.reasoning_effort=high"], cwd=tmp_path).model.reasoning_effort == "high"


def test_a_thinking_budget_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    with pytest.raises(ValidationError, match="unknown reasoning effort"):
        load_config(["model.reasoning_effort=huge"], cwd=tmp_path)


def test_the_history_of_the_sessions_is_kept_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    config = load_config([], cwd=tmp_path)
    assert config.history.persistence == "save-all"
    assert config.history.max_bytes == 0


def test_the_history_may_not_be_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    assert load_config(["history.persistence=save-none"], cwd=tmp_path).history.persistence == "save-none"


def test_a_persistence_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    with pytest.raises(ValidationError, match="unknown persistence"):
        load_config(["history.persistence=maybe"], cwd=tmp_path)


def test_the_history_may_have_a_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    assert load_config(["history.max_bytes=1000"], cwd=tmp_path).history.max_bytes == 1000


def test_the_file_opener_is_read_from_the_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    assert load_config(["ui.file_opener=vscode"], cwd=tmp_path).ui.file_opener == "vscode"


def test_the_keys_that_nobody_reads_are_gone():
    """The settings that nothing reads are not settings any more."""
    assert not hasattr(Config().ui, "theme")
    assert not hasattr(Config().ui, "show_reasoning")


def test_a_file_with_the_keys_that_are_gone_still_loads(tmp_path, monkeypatch):
    """A key that does not exist is ignored, so an old file is not a broken file."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True)
    project.write_text("ui:\n  theme: dark\n  show_reasoning: false\n", encoding="utf-8")
    assert load_config([], cwd=tmp_path).ui.approval_timeout == 0


def _user_config(tmp_path, monkeypatch, text: str) -> None:
    """The configuration of the user."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    (home / "config.yaml").write_text(text, encoding="utf-8")


def test_a_profile_is_used_when_it_is_selected(tmp_path, monkeypatch):
    _user_config(
        tmp_path,
        monkeypatch,
        "profiles:\n  fast:\n    model:\n      model_name: cheap/model\n    agent:\n      max_turns: 3\n",
    )
    config = load_config(["profile=fast"], cwd=tmp_path)
    assert config.model.model_name == "cheap/model"
    assert config.agent.max_turns == 3


def test_a_profile_that_is_not_selected_is_not_used(tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch, "profiles:\n  fast:\n    agent:\n      max_turns: 3\n")
    assert load_config([], cwd=tmp_path).agent.max_turns == 50


def test_the_user_may_select_a_profile_in_the_configuration(tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch, "profile: fast\nprofiles:\n  fast:\n    agent:\n      max_turns: 3\n")
    assert load_config([], cwd=tmp_path).agent.max_turns == 3


def test_a_profile_wins_over_the_configuration_of_the_user(tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch, "agent:\n  max_turns: 9\nprofiles:\n  fast:\n    agent:\n      max_turns: 3\n")
    assert load_config(["profile=fast"], cwd=tmp_path).agent.max_turns == 3


def test_the_command_line_wins_over_the_profile(tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch, "profiles:\n  fast:\n    agent:\n      max_turns: 3\n")
    assert load_config(["profile=fast", "agent.max_turns=5"], cwd=tmp_path).agent.max_turns == 5


def test_a_profile_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch, "profiles:\n  fast:\n    agent:\n      max_turns: 3\n")
    with pytest.raises(ValueError, match="unknown profile 'slow'"):
        load_config(["profile=slow"], cwd=tmp_path)


def test_the_profile_of_the_project_is_not_used(tmp_path, monkeypatch):
    """Choosing a set of permissions is the decision of the user."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True)
    project.write_text("profile: fast\nprofiles:\n  fast:\n  agent:\n    max_turns: 3\n", encoding="utf-8")
    config = load_config([], cwd=tmp_path)
    assert config.agent.max_turns == 50
    assert config.profiles == {}


def test_a_profile_may_not_open_a_sandbox_the_project_closed(tmp_path, monkeypatch):
    _user_config(
        tmp_path,
        monkeypatch,
        "profiles:\n  fast:\n    sandbox:\n      mode: full-access\n",
    )
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True)
    project.write_text("sandbox:\n  mode: read-only\n", encoding="utf-8")
    assert load_config(["profile=fast"], cwd=tmp_path).sandbox.mode == "read-only"
