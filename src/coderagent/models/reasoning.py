"""How much a model thinks, in the words of its provider.

The user asks for a level (`minimal`, `low`, `medium`, `high`) and every
provider names it differently: OpenAI wants `reasoning_effort`, Anthropic wants
a number of tokens to think with. The translation happens here, once.
"""

from typing import Any

from coderagent.models.provider import provider_of

EFFORTS = ("minimal", "low", "medium", "high")
"""The levels the user may ask for. Empty means: the default of the model."""

BUDGETS = {"minimal": 1024, "low": 2048, "medium": 8192, "high": 16384}
"""The tokens of thinking, for the providers that count tokens and not levels.

Anthropic asks for at least 1024 tokens, so `minimal` is that.
"""


def translate(model_name: str, effort: str) -> dict[str, Any]:
    """The parameter the provider of this model understands."""
    if effort not in EFFORTS:
        raise ValueError(f"unknown reasoning effort '{effort}'. Use one of: {', '.join(EFFORTS)}.")
    if provider_of(model_name) == "anthropic":
        return {"thinking": {"type": "enabled", "budget_tokens": BUDGETS[effort]}}
    return {"reasoning_effort": effort}
