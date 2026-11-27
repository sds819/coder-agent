"""The settings of the model: the layers merged, the secrets taken out.

The terminal, the terminal interface and the browser all show the same eight
things: the name of the model, the provider, the address, whether a key is
set, where the key comes from and how many times a call is tried at most.
"""

import os
from pathlib import Path
from typing import Any

from coderagent.config.loader import load_config
from coderagent.config.schema import ModelConfig
from coderagent.models.litellm_config import resolve as resolve_alias
from coderagent.models.provider import env_key, env_var, normalize
from coderagent.models.provider import provider_of as provider_of_model


def hint(secret: str) -> str:
    """A hint of a secret: enough to recognize it, too little to use it."""
    if not secret:
        return ""
    return f"********{secret[-4:]}" if len(secret) > 4 else "********"


def api_base_of(endpoint: str) -> str:
    """The base of an endpoint: litellm adds the path of the chat completions itself.

    The providers hand out the full address
    (`https://api.example.com/v1/chat/completions`), the base stops at `/v1`.
    """
    base = endpoint.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def provider_of(model_name: str, api_base: str = "") -> str:
    """The provider of a model: the name says it, the endpoint does, the family does."""
    return provider_of_model(model_name, api_base)


def env_api_key(model_name: str, api_base: str = "") -> str:
    """The key the environment has for the provider of the model."""
    return env_key(model_name, api_base)


def key_source(own_key: str, provider: str) -> str:
    """Where the key comes from: the settings, or the environment of the provider."""
    if own_key:
        return "settings"
    return "env" if os.getenv(env_var(provider), "") else ""


def key_of(effective: dict) -> str:
    """The key of a run: the one of the settings or the one of the environment."""
    kwargs = effective["model_kwargs"]
    return str(kwargs.get("api_key") or env_api_key(effective["model_name"], str(kwargs.get("api_base") or "")))


def effective_of(model: ModelConfig, overrides: dict) -> dict:
    """The model to talk to and the kwargs to talk with, with the overrides applied.

    An alias of a litellm config file is resolved here: the name becomes the
    model of the provider and the parameters of the alias are the kwargs.
    """
    kwargs = dict(model.model_kwargs)
    if model.api_key:
        kwargs["api_key"] = model.api_key
        """The field of its own wins over the old place of `model_kwargs`."""
    if model.api_base:
        kwargs["api_base"] = model.api_base
    name = model.model_name
    aliases = model.litellm_config
    if isinstance(overrides.get("model_name"), str) and overrides["model_name"].strip():
        name = overrides["model_name"].strip()
    if isinstance(overrides.get("litellm_config"), str) and overrides["litellm_config"].strip():
        aliases = overrides["litellm_config"].strip()
    for key in ("api_base", "api_key"):
        value = overrides.get(key)
        if isinstance(value, str):
            if value.strip():
                kwargs[key] = api_base_of(value) if key == "api_base" else value.strip()
            else:
                kwargs.pop(key, None)
    extra = overrides.get("model_kwargs")
    if isinstance(extra, dict):
        kwargs.update({key: value for key, value in extra.items() if key not in ("api_key", "api_base")})
    resolved, params = resolve_alias(aliases, name)
    merged = params | kwargs
    base = str(merged.get("api_base") or "")
    return {
        "model_name": normalize(resolved, base),
        "requested": name,
        "alias": name if resolved != name else "",
        "provider": provider_of(resolved, base),
        "litellm_config": aliases,
        "model_kwargs": merged,
        "reasoning_effort": model.reasoning_effort,
    }


def effective_model(cwd: Path, overrides: dict) -> dict:
    """The model of a run: the layers merged, with the overrides applied."""
    return effective_of(load_config([], cwd=cwd).model, overrides)


def effective_api_key(cwd: Path) -> str:
    """The key the agent would use: the one of the settings, the one of the alias or the one of the environment."""
    config = load_config([], cwd=cwd)
    name, params = resolve_alias(config.model.litellm_config, config.model.model_name)
    base = str(config.model.api_base or config.model.model_kwargs.get("api_base") or params.get("api_base") or "")
    key = (
        config.model.api_key
        or config.model.model_kwargs.get("api_key")
        or params.get("api_key")
        or env_api_key(name, base)
    )
    return str(key or "")


def model_view_of(model: ModelConfig) -> dict[str, Any]:
    """The settings of a model, with the secrets taken out.

    Only the settings the settings page shows are here: the rest of the model
    lives in the configuration file, and the file is the only place it is read
    from.
    """
    kwargs = dict(model.model_kwargs)
    resolved, alias = resolve_alias(model.litellm_config, model.model_name)
    base = str(model.api_base or kwargs.get("api_base") or alias.get("api_base") or "")
    provider = provider_of(resolved, base)
    own_key = model.api_key or kwargs.get("api_key") or alias.get("api_key")
    key = own_key or env_api_key(resolved, base)
    return {
        "model_name": model.model_name,
        "provider": provider,
        "api_base": str(model.api_base or kwargs.get("api_base") or ""),
        "api_key_set": bool(key),
        "api_key_hint": hint(key),
        "key_source": key_source(own_key, provider),
        "key_env": env_var(provider),
        "max_retries": model.max_retries,
    }


def model_view(cwd: Path) -> dict[str, Any]:
    """The settings of the model of a directory, with the secrets taken out."""
    return model_view_of(load_config([], cwd=cwd).model)


def key_text(view: dict) -> str:
    """The key of a view, in a line: whether it is set and where it comes from."""
    if not view.get("api_key_set"):
        return "not set"
    source = "the settings" if view.get("key_source") == "settings" else f"the environment ({view.get('key_env', '')})"
    return f"set ({view.get('api_key_hint', '')}) from {source}"


def view_text(view: dict, path: str = "") -> str:
    """The settings of the model, as the terminal and the interface show them."""
    lines = [
        f"model: {view.get('model_name', '')}",
        f"provider: {view.get('provider', '') or '(none)'}",
        f"api base: {view.get('api_base', '') or '(none)'}",
        f"api key: {key_text(view)}",
        f"max retries: {view.get('max_retries', 0)}",
    ]
    if path:
        lines.append(f"file: {path}")
    return "\n".join(lines)
