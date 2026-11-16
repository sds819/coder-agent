"""The number of attempts of a model call comes from the configuration."""

import logging

from coderagent.config.schema import Config
from coderagent.models.backends import LiteLLMBackend
from coderagent.models.router import ModelRouter
from coderagent.run import build_model
from minisweagent.models.utils.retry import retry


def _attempts(attempts: int = 0) -> int:
    """How many times the retry would try."""
    return retry(logger=logging.getLogger("test"), abort_exceptions=[], attempts=attempts).stop.max_attempt_number


def test_the_configuration_says_how_many_times_a_call_is_tried(monkeypatch):
    monkeypatch.delenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", raising=False)
    assert _attempts(3) == 3


def test_without_a_number_ten_times_are_tried(monkeypatch):
    monkeypatch.delenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", raising=False)
    assert _attempts() == 10


def test_the_environment_wins_over_the_configuration(monkeypatch):
    monkeypatch.setenv("MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT", "1")
    assert _attempts(3) == 1


def test_the_model_of_the_session_tries_the_number_of_the_configuration():
    config = Config()
    config.model.max_retries = 2
    assert build_model(config).max_retries == 2


def test_the_model_of_the_routing_tries_the_number_too():
    config = Config()
    config.model.max_retries = 2
    assert ModelRouter(config.model).backend_for("openai/gpt-5").max_retries == 2


def test_a_backend_without_a_number_lets_the_retry_decide():
    assert LiteLLMBackend("openai/gpt-5").max_retries == 0
