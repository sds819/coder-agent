"""Model backends. Reuses mini-swe-agent's retry and cache-control primitives."""

import logging
from collections.abc import Iterator
from functools import cache
from typing import Any

import litellm

from coderagent.models.litellm_config import resolve as resolve_alias
from coderagent.models.reasoning import translate
from coderagent.models.streaming import ModelEvent, ToolCallAccumulator, message_from_events
from minisweagent.models.utils.cache_control import set_cache_control
from minisweagent.models.utils.retry import retry

logger = logging.getLogger("coderagent.backend")

AUTH_HINTS = ("api key", "apikey", "invalid token", "unauthorized", "authentication", "no api key")
"""What a provider says when the key is the problem and not the server."""


def is_auth_error(error: Exception) -> bool:
    """Whether the error says that the key is wrong.

    A relay station without a key answers with a 500, and a 500 is worth
    retrying. This one is not: the key will not become good by waiting.
    """
    text = str(error).lower()
    return any(hint in text for hint in AUTH_HINTS)


@cache
def _warn_about_the_price(model: str, message: str) -> None:
    """Say that the price of a model is missing, once and not on every call.

    A model that has no price has no cost: the budget of such a model is
    `agent.token_limit`, and the money never moves.
    """
    logger.warning("Could not calculate cost for model %s: %s", model, message)


class LiteLLMBackend:
    """Calls `litellm.completion` and normalizes the response."""

    abort_exceptions: list[type[Exception]] = [
        litellm.exceptions.UnsupportedParamsError,
        litellm.exceptions.NotFoundError,
        litellm.exceptions.PermissionDeniedError,
        litellm.exceptions.ContextWindowExceededError,
        litellm.exceptions.AuthenticationError,
        litellm.exceptions.BadRequestError,
        KeyboardInterrupt,
    ]

    def __init__(
        self,
        model_name: str,
        *,
        model_kwargs: dict[str, Any] | None = None,
        set_cache_control: str | None = None,
        litellm_config: str = "",
        reasoning_effort: str = "",
        max_retries: int = 0,
    ) -> None:
        """The name may be an alias of the model list of a litellm config file."""
        name, params = resolve_alias(litellm_config, model_name) if litellm_config else (model_name, {})
        self.model_name = name
        self.model_kwargs = params | (model_kwargs or {})
        if reasoning_effort:
            """The thinking budget, in the words of the provider of this model."""
            for key, value in translate(name, reasoning_effort).items():
                self.model_kwargs.setdefault(key, value)
                """What the user wrote in `model_kwargs` wins over the level."""
        self.set_cache_control = set_cache_control
        self.max_retries = max_retries
        """How many times a call is tried at most. 0 lets the retry decide."""

    def query(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> dict:
        return message_from_events(self.query_stream(messages, tools=tools, **kwargs))

    def query_stream(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> Iterator[ModelEvent]:
        """The answer as it arrives: text, reasoning and tool call fragments."""
        prepared = set_cache_control(
            [{k: v for k, v in message.items() if k != "extra"} for message in messages],
            mode=self.set_cache_control,
        )
        call_kwargs = self.model_kwargs | kwargs
        if tools:
            call_kwargs["tools"] = tools
        call_kwargs["stream"] = True
        call_kwargs.setdefault("stream_options", {"include_usage": True})
        yield from self._events(self._open_stream(prepared, call_kwargs))

    def get_template_vars(self) -> dict[str, Any]:
        return {"model_name": self.model_name, **self.model_kwargs}

    def _open_stream(self, messages: list[dict], call_kwargs: dict):
        for attempt in retry(logger=logger, abort_exceptions=self.abort_exceptions, attempts=self.max_retries):
            with attempt:
                try:
                    return litellm.completion(model=self.model_name, messages=messages, **call_kwargs)
                except litellm.exceptions.InternalServerError as e:
                    if is_auth_error(e):
                        """The key is wrong. Retrying only makes the user wait longer."""
                        raise litellm.exceptions.AuthenticationError(
                            str(e), getattr(e, "llm_provider", "") or "", self.model_name
                        ) from e
                    raise
        raise RuntimeError("the retry loop ended without a response")

    def _events(self, response) -> Iterator[ModelEvent]:
        accumulator = ToolCallAccumulator()
        for chunk in response:
            delta = self._delta(chunk)
            if delta is not None:
                reasoning = self._field(delta, "reasoning_content") or self._field(delta, "reasoning")
                if reasoning:
                    yield ModelEvent(type="reasoning", content=reasoning)
                text = self._field(delta, "content")
                if text:
                    yield ModelEvent(type="text", content=text)
                for fragment in self._tool_call_fragments(delta):
                    accumulator.feed(fragment)
                    yield ModelEvent(type="tool_call_delta", raw=fragment)
            usage = self._field(chunk, "usage")
            if usage:
                yield ModelEvent(type="usage", cost=self._stream_cost(usage), raw={"usage": usage})
        for call in accumulator.finish():
            yield ModelEvent(type="tool_call_done", tool_call=call)

    @staticmethod
    def _delta(chunk) -> Any:
        choices = getattr(chunk, "choices", None) or []
        return getattr(choices[0], "delta", None) if choices else None

    @staticmethod
    def _field(obj, name: str):
        value = getattr(obj, name, None)
        if value is None and isinstance(obj, dict):
            value = obj.get(name)
        return value

    @staticmethod
    def _tool_call_fragments(delta) -> list[dict]:
        fragments = []
        for call in getattr(delta, "tool_calls", None) or []:
            if isinstance(call, dict):
                fragments.append(call)
            elif hasattr(call, "model_dump"):
                fragments.append(call.model_dump())
            else:  # pragma: no cover - providers always give one of the two
                function = getattr(call, "function", None)
                fragments.append(
                    {
                        "index": getattr(call, "index", 0),
                        "id": getattr(call, "id", "") or "",
                        "function": {
                            "name": getattr(function, "name", "") or "",
                            "arguments": getattr(function, "arguments", "") or "",
                        },
                    }
                )
        return fragments

    def _stream_cost(self, usage) -> float:
        prompt = int(self._field(usage, "prompt_tokens") or 0)
        completion = int(self._field(usage, "completion_tokens") or 0)
        try:
            prompt_cost, completion_cost = litellm.cost_calculator.cost_per_token(
                model=self.model_name, prompt_tokens=prompt, completion_tokens=completion
            )
            return float(prompt_cost) + float(completion_cost)
        except Exception as e:
            _warn_about_the_price(self.model_name, str(e))
            return 0.0
