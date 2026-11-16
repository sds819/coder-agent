"""The thinking budget, in the words of the provider of the model."""

import pytest

from coderagent.models.backends import LiteLLMBackend
from coderagent.models.reasoning import BUDGETS, translate


def test_an_openai_model_wants_a_level():
    assert translate("openai/o3-mini", "high") == {"reasoning_effort": "high"}


def test_an_anthropic_model_wants_a_number_of_tokens():
    assert translate("anthropic/claude-sonnet-4-5", "high") == {
        "thinking": {"type": "enabled", "budget_tokens": BUDGETS["high"]}
    }


def test_the_tokens_of_anthropic_are_never_below_its_minimum():
    """Anthropic asks for at least 1024 tokens of thinking."""
    assert all(budget >= 1024 for budget in BUDGETS.values())


def test_a_level_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="unknown reasoning effort"):
        translate("openai/o3-mini", "huge")


def test_the_level_goes_into_the_parameters_of_the_call():
    backend = LiteLLMBackend("openai/o3-mini", reasoning_effort="low")
    assert backend.model_kwargs["reasoning_effort"] == "low"


def test_the_parameters_the_user_wrote_win_over_the_level():
    backend = LiteLLMBackend(
        "openai/o3-mini",
        model_kwargs={"reasoning_effort": "minimal"},
        reasoning_effort="high",
    )
    assert backend.model_kwargs["reasoning_effort"] == "minimal"


def test_a_model_without_a_level_sends_nothing():
    assert LiteLLMBackend("openai/o3-mini").model_kwargs == {}


def test_the_alias_of_a_model_is_translated_with_the_model_behind_it(tmp_path):
    """The alias names the model; the provider of the model behind it decides."""
    path = tmp_path / "litellm_config.yaml"
    path.write_text(
        "model_list:\n  - model_name: mine/claude\n    litellm_params:\n      model: anthropic/claude-sonnet-4-5\n",
        encoding="utf-8",
    )
    backend = LiteLLMBackend("mine/claude", litellm_config=str(path), reasoning_effort="medium")
    assert backend.model_kwargs["thinking"] == {"type": "enabled", "budget_tokens": BUDGETS["medium"]}
