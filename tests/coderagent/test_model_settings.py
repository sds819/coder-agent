"""The settings of the model: the file of the user, the view and the try-out."""

import pytest
import yaml

from coderagent.config import writer
from coderagent.models import check, settings
from coderagent.models.provider import PROVIDERS
from coderagent.paths import config_home


@pytest.fixture(autouse=True)
def _no_model_in_the_environment(monkeypatch):
    """The environment of the user must not decide what the test expects."""
    monkeypatch.delenv("MSWEA_MODEL_NAME", raising=False)
    for name in PROVIDERS.values():
        monkeypatch.delenv(name, raising=False)


def _user_file() -> dict:
    """The configuration file of the user, as it is on the disk."""
    path = config_home() / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def test_the_settings_are_written_to_the_user_file(tmp_path):
    (tmp_path / ".coderagent").mkdir()
    (tmp_path / ".coderagent" / "config.yaml").write_text("model:\n  model_name: other/model\n", encoding="utf-8")

    path = writer.write_user_model({"model_name": "deepseek/deepseek-flash"})

    assert path == config_home() / "config.yaml"
    assert _user_file()["model"]["model_name"] == "deepseek/deepseek-flash"
    assert "deepseek" not in (tmp_path / ".coderagent" / "config.yaml").read_text(encoding="utf-8")
    """The project level file is never written: it is in the repository."""


def test_a_setting_that_is_the_default_is_not_written():
    writer.write_user_model({"model_name": "deepseek/deepseek-flash", "max_retries": 3, "set_cache_control": None})

    assert _user_file()["model"] == {"model_name": "deepseek/deepseek-flash"}
    """The default may change: the user who never touched it must get the new one."""


def test_an_empty_key_removes_the_key():
    writer.write_user_model({"api_key": "sk-secret-value"})

    writer.write_user_model({"api_key": ""})

    assert "api_key" not in (_user_file().get("model") or {})


def test_a_key_that_is_not_given_keeps_the_one_that_is_set():
    writer.write_user_model({"api_key": "sk-secret-value"})

    writer.write_user_model({"model_name": "deepseek/deepseek-flash"})

    assert _user_file()["model"]["api_key"] == "sk-secret-value"


def test_a_model_that_does_not_work_is_written_all_the_same():
    """The write never calls the model: a setting to fix later is worth writing down."""
    writer.write_user_model({"model_name": "not-a-real-provider/nope"})

    assert _user_file()["model"]["model_name"] == "not-a-real-provider/nope"


def test_the_view_shows_the_eight_settings(tmp_path):
    view = settings.model_view(tmp_path)

    assert sorted(view) == [
        "api_base",
        "api_key_hint",
        "api_key_set",
        "key_env",
        "key_source",
        "max_retries",
        "model_name",
        "provider",
    ]


def test_the_view_says_the_provider_and_where_the_key_comes_from(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-value")
    writer.write_user_model({"model_name": "deepseek/deepseek-flash"})

    view = settings.model_view(tmp_path)

    assert view["provider"] == "deepseek"
    assert view["key_source"] == "env"
    assert view["key_env"] == "DEEPSEEK_API_KEY"
    assert view["api_key_set"] is True
    assert view["api_key_hint"] == "********" + "sk-env-value"[-4:]


def test_the_try_out_never_writes():
    """The try-out says whether the settings work; the writing is a step of its own."""
    report = check.test_connection({"model_name": "not-a-real-provider/nope", "model_kwargs": {}})

    assert report["ok"] is False
    assert not (config_home() / "config.yaml").exists()


def test_the_view_text_says_the_key_and_the_file():
    text = settings.view_text(
        {
            "model_name": "openai/MiniMax-M2.7",
            "provider": "openai",
            "api_base": "https://api.nengpa.com/v1",
            "api_key_set": True,
            "api_key_hint": "********abcd",
            "key_source": "env",
            "key_env": "OPENAI_API_KEY",
            "max_retries": 3,
        },
        "/home/x/.coderagent/config.yaml",
    )

    assert "model: openai/MiniMax-M2.7" in text
    assert "provider: openai" in text
    assert "api base: https://api.nengpa.com/v1" in text
    assert "the environment (OPENAI_API_KEY)" in text
    assert "file: /home/x/.coderagent/config.yaml" in text
