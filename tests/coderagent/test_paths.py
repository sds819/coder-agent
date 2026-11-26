"""The keys of the models: where they come from and who wins."""

import os

from coderagent.paths import config_home, global_env_file, load_global_env


def test_the_keys_of_the_coding_agent_are_read(tmp_path, monkeypatch):
    """The file of the coding agent holds the keys of the models."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path))
    monkeypatch.delenv("SOME_MODEL_KEY", raising=False)
    (tmp_path / ".env").write_text("SOME_MODEL_KEY=from-the-coder\n")

    load_global_env()

    assert os.environ["SOME_MODEL_KEY"] == "from-the-coder"


def test_the_file_of_mini_swe_agent_is_read_too(tmp_path, monkeypatch):
    """The users of mini-swe-agent keep their keys where mini-swe-agent put them."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "coder"))
    monkeypatch.setenv("MSWEA_GLOBAL_CONFIG_DIR", str(tmp_path / "mini"))
    monkeypatch.delenv("SOME_MODEL_KEY", raising=False)
    (tmp_path / "mini").mkdir()
    (tmp_path / "mini" / ".env").write_text("SOME_MODEL_KEY=from-mini\n")

    load_global_env()

    assert os.environ["SOME_MODEL_KEY"] == "from-mini"


def test_the_file_of_the_coding_agent_wins(tmp_path, monkeypatch):
    """Two files, one key: the one of the coding agent wins."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "coder"))
    monkeypatch.setenv("MSWEA_GLOBAL_CONFIG_DIR", str(tmp_path / "mini"))
    monkeypatch.delenv("SOME_MODEL_KEY", raising=False)
    (tmp_path / "coder").mkdir()
    (tmp_path / "mini").mkdir()
    (tmp_path / "coder" / ".env").write_text("SOME_MODEL_KEY=from-the-coder\n")
    (tmp_path / "mini" / ".env").write_text("SOME_MODEL_KEY=from-mini\n")

    load_global_env()

    assert os.environ["SOME_MODEL_KEY"] == "from-the-coder"


def test_the_environment_of_the_shell_wins(tmp_path, monkeypatch):
    """The shell of the user is closer to the model than a file."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path))
    monkeypatch.setenv("SOME_MODEL_KEY", "from-the-shell")
    (tmp_path / ".env").write_text("SOME_MODEL_KEY=from-the-file\n")

    load_global_env()

    assert os.environ["SOME_MODEL_KEY"] == "from-the-shell"


def test_a_missing_file_is_not_an_error(tmp_path, monkeypatch):
    """A user without keys has no file: the agent still starts."""
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "coder"))
    monkeypatch.setenv("MSWEA_GLOBAL_CONFIG_DIR", str(tmp_path / "mini"))

    load_global_env()

    assert not config_home().joinpath(".env").exists()
    assert not global_env_file().exists()
