"""The name of a model says the provider, or the endpoint does, or the family does."""

from coderagent.models.provider import (
    FAMILIES,
    PROVIDERS,
    env_key,
    env_var,
    normalize,
    provider_of,
    split,
)


def test_a_slash_says_the_provider():
    assert split("openai/MiniMax-M2.7") == ("openai", "MiniMax-M2.7")


def test_a_colon_says_the_provider_too():
    assert split("openai:MiniMax-M2.7") == ("openai", "MiniMax-M2.7")


def test_a_colon_of_something_else_is_part_of_the_name():
    """The name of a fine tuned model has colons in it: it is one name."""
    assert split("ft:gpt-4o:acme") == ("", "ft:gpt-4o:acme")


def test_a_name_without_a_provider_stays_one_name():
    assert split("MiniMax-M2.7") == ("", "MiniMax-M2.7")


def test_the_provider_of_the_name_wins_over_everything():
    assert provider_of("anthropic/claude-sonnet-4-5", "https://api.example.com/v1") == "anthropic"
    assert provider_of("openai:MiniMax-M2.7", "https://api.anthropic.com/v1") == "openai"


def test_the_endpoint_says_the_protocol():
    assert provider_of("MiniMax-M2.7", "https://api.anthropic.com/v1") == "anthropic"
    assert provider_of("MiniMax-M2.7", "https://api.nengpa.com/v1") == "openai"


def test_the_family_says_the_provider():
    assert provider_of("gpt-4o") == "openai"
    assert provider_of("claude-sonnet-4-5") == "anthropic"
    assert provider_of("gemini-2.5-pro") == "gemini"
    assert provider_of("deepseek-chat") == "deepseek"
    assert provider_of("grok-4") == "xai"
    assert provider_of("qwen3-coder-plus") == "dashscope"
    assert provider_of("kimi-k2.5") == "moonshot"
    assert provider_of("minimax-m2") == "minimax"
    assert provider_of("mistral-large") == "mistral"
    assert provider_of("command-r-plus") == "cohere"
    assert provider_of("sonar-pro") == "perplexity"


def test_a_name_that_says_nothing_stays_as_it_is():
    assert provider_of("some-model-nobody-knows") == ""
    assert normalize("some-model-nobody-knows") == "some-model-nobody-knows"


def test_the_name_litellm_is_called_with_carries_the_provider():
    assert normalize("openai/MiniMax-M2.7") == "openai/MiniMax-M2.7"
    assert normalize("openai:MiniMax-M2.7") == "openai/MiniMax-M2.7"
    assert normalize("MiniMax-M2.7") == "minimax/MiniMax-M2.7"
    assert normalize("MiniMax-M2.7", "https://api.nengpa.com/v1") == "openai/MiniMax-M2.7"


def test_the_provider_of_a_name_is_not_rewritten():
    """The name of the user is what the file keeps: the resolution happens at the call."""
    assert normalize("not-a-real-provider/nope") == "not-a-real-provider/nope"


def test_every_provider_has_a_key():
    assert PROVIDERS["dashscope"] == "DASHSCOPE_API_KEY"
    assert PROVIDERS["minimax"] == "MINIMAX_API_KEY"
    assert env_var("openai") == "OPENAI_API_KEY"
    assert env_var("nobody") == ""


def test_the_key_of_the_environment_is_the_one_of_the_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-env")
    assert env_key("minimax/minimax-m2") == "sk-env"
    assert env_key("MiniMax-M2.7") == "sk-env"
    assert env_key("openai/gpt-4o") == ""


def test_the_families_are_the_ones_of_litellm():
    assert all(provider in PROVIDERS for provider in FAMILIES.values())
