"""The aliases of a litellm config file name the models."""

import logging

from coderagent.models.backends import LiteLLMBackend
from coderagent.models.litellm_config import deployments, locate, resolve

CONFIG = """
model_list:
  - model_name: nengpa/minimax-m2.7
    litellm_params:
      model: openai/MiniMax-M2.7
      api_base: https://api.nengpa.com/v1
      api_key: sk-cp-secret
"""


def _write(tmp_path, content: str = CONFIG) -> str:
    path = tmp_path / "litellm_config.yaml"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_an_alias_names_the_model_and_its_parameters(tmp_path):
    assert resolve(_write(tmp_path), "nengpa/minimax-m2.7") == (
        "openai/MiniMax-M2.7",
        {"api_base": "https://api.nengpa.com/v1", "api_key": "sk-cp-secret"},
    )


def test_a_name_that_is_not_an_alias_stays_as_it_is(tmp_path):
    assert resolve(_write(tmp_path), "openai/gpt-4o") == ("openai/gpt-4o", {})


def test_a_name_that_is_not_an_alias_is_told_that_the_file_is_of_no_use(tmp_path, caplog):
    """The file is silently of no use otherwise: the user does not know why."""
    with caplog.at_level(logging.WARNING, logger="coderagent.models.litellm_config"):
        resolve(_write(tmp_path), "openai/gpt-4o")
    assert [record.getMessage() for record in caplog.records] == [
        f"The model 'openai/gpt-4o' is not one of the aliases of {_write(tmp_path)} "
        "(nengpa/minimax-m2.7): the settings of that file are not used."
    ]


def test_a_name_that_is_an_alias_is_not_complained_about(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="coderagent.models.litellm_config"):
        resolve(_write(tmp_path), "nengpa/minimax-m2.7")
    assert caplog.records == []


def test_a_file_that_is_not_there_is_not_complained_about(tmp_path, caplog):
    """There is no file: there is nothing to be of no use."""
    with caplog.at_level(logging.WARNING, logger="coderagent.models.litellm_config"):
        resolve(str(tmp_path / "nope.yaml"), "openai/gpt-4o")
    assert caplog.records == []


def test_a_file_that_is_not_there_has_no_aliases(tmp_path):
    assert resolve(str(tmp_path / "nope.yaml"), "nengpa/minimax-m2.7") == ("nengpa/minimax-m2.7", {})
    assert deployments(str(tmp_path / "nope.yaml")) == {}


def test_no_file_at_all_has_no_aliases():
    assert resolve("", "nengpa/minimax-m2.7") == ("nengpa/minimax-m2.7", {})


def test_the_backend_takes_the_model_and_the_key_from_the_alias(tmp_path):
    backend = LiteLLMBackend("nengpa/minimax-m2.7", litellm_config=_write(tmp_path))
    assert backend.model_name == "openai/MiniMax-M2.7"
    assert backend.model_kwargs == {"api_base": "https://api.nengpa.com/v1", "api_key": "sk-cp-secret"}


def test_the_settings_of_the_configuration_win_over_the_alias(tmp_path):
    backend = LiteLLMBackend(
        "nengpa/minimax-m2.7",
        model_kwargs={"api_key": "sk-other"},
        litellm_config=_write(tmp_path),
    )
    assert backend.model_kwargs == {"api_base": "https://api.nengpa.com/v1", "api_key": "sk-other"}


def test_a_relative_path_is_looked_for_in_the_home_of_the_user(tmp_path, monkeypatch):
    """The setting lives in a file that does not move: the path does not move either."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    (home / "litellm_config.yaml").write_text(CONFIG, encoding="utf-8")
    assert resolve("litellm_config.yaml", "nengpa/minimax-m2.7")[0] == "openai/MiniMax-M2.7"


def test_a_relative_path_is_looked_for_in_the_working_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    (tmp_path / "litellm_config.yaml").write_text(CONFIG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve("litellm_config.yaml", "nengpa/minimax-m2.7")[0] == "openai/MiniMax-M2.7"


def test_a_relative_path_that_is_nowhere_says_where_it_was_looked_for(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    assert locate("nope.yaml") == home / "nope.yaml"
