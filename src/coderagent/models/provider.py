"""The provider of a model: which one it is, and which key it uses.

One rule, one place. The name of a model may carry the provider
(`openai/MiniMax-M2.7`, `openai:MiniMax-M2.7`) or not (`MiniMax-M2.7`).
When it does not, the address of the endpoint says the protocol, and the
family of the model says the provider. What is still unknown stays as it is:
the name of the user is never rewritten behind their back.
"""

import os

PROVIDERS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "fireworks_ai": "FIREWORKS_API_KEY",
    "azure": "AZURE_API_KEY",
    "cohere": "COHERE_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "perplexity": "PERPLEXITYAI_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "minimax": "MINIMAX_API_KEY",
}
"""The provider of a model and the environment variable of its key."""

FAMILIES = {
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "claude": "anthropic",
    "gemini": "gemini",
    "deepseek": "deepseek",
    "grok": "xai",
    "qwen": "dashscope",
    "kimi": "moonshot",
    "minimax": "minimax",
    "mistral": "mistral",
    "command": "cohere",
    "sonar": "perplexity",
}
"""The family of a model says the provider, when the name does not."""


def split(name: str) -> tuple[str, str]:
    """The provider and the model of a name.

    A slash always counts. A colon counts only when what is in front of it is
    a known provider: `ft:gpt-4o:acme` is one name.
    """
    head, sep, tail = name.partition("/")
    if sep:
        return head.lower(), tail
    head, sep, tail = name.partition(":")
    if sep and head.lower() in PROVIDERS:
        return head.lower(), tail
    return "", name


def provider_of(name: str, api_base: str = "") -> str:
    """The provider of a model: the name says it, the endpoint does, the family does."""
    provider, model = split(name)
    if provider:
        return provider
    if api_base:
        """The address speaks for itself: Anthropic, or the OpenAI protocol every relay speaks."""
        return "anthropic" if "anthropic" in api_base.lower() else "openai"
    for prefix, provider in FAMILIES.items():
        if model.lower().startswith(prefix):
            return provider
    return ""


def normalize(name: str, api_base: str = "") -> str:
    """The name litellm is called with: the provider in front of the model.

    A name that says nothing about its provider stays as it is.
    """
    provider, model = split(name)
    provider = provider or provider_of(name, api_base)
    return f"{provider}/{model}" if provider else name


def env_var(provider: str) -> str:
    """The environment variable of the key of a provider."""
    return PROVIDERS.get(provider, "")


def env_key(name: str, api_base: str = "") -> str:
    """The key the environment has for this model."""
    return os.getenv(env_var(provider_of(name, api_base)), "")
