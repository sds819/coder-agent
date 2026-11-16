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
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MSWEA_MODEL_NAME", "deepseek/deepseek-flash")
    project = tmp_path / ".coderagent" / "config.yaml"
    project.parent.mkdir(parents=True)
    project.write_text("model:\n  model_name: openai/gpt-5\n", encoding="utf-8")
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
