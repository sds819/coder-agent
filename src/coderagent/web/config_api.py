"""The model configuration as the browser sees it: merged, layered and without secrets.

The api key is only ever written to the user level configuration file, and it
never leaves the server in clear text.
"""

import os
import time
from pathlib import Path
from typing import Any

import yaml

from coderagent.config.loader import DEFAULTS_PATH, config_layers, load_config
from coderagent.config.schema import PURPOSES, ModelConfig, PermissionConfig, check_routing_rule
from coderagent.models.call import check_reserved
from coderagent.models.litellm_config import locate
from coderagent.models.litellm_config import resolve as resolve_alias
from coderagent.models.provider import PROVIDERS, env_key, env_var, normalize
from coderagent.models.provider import provider_of as provider_of_model
from coderagent.models.reasoning import EFFORTS
from coderagent.models.verbosity import VERBOSITIES
from coderagent.paths import config_home
from coderagent.tools.permissions import PermissionMode

PERMISSION_MODES = [mode.value for mode in PermissionMode]
"""The permission modes the browser can choose from."""

PERMISSION_FIELDS = ("mode", "deny_paths", "include_dirs", "network")
"""The permission settings that live directly under `permissions:`."""

NETWORK_POLICIES = ("allow", "deny")
"""What the browser may choose for the network."""

SECRET_FIELDS = ("api_base", "api_key")
"""The settings of the model that have a field of their own, next to `model_kwargs`."""

ENV_KEYS = PROVIDERS
"""The environment variable of the key of a provider. The name of the model says which provider it is."""


def hint(secret: str) -> str:
    """A hint of a secret: enough to recognize it, too little to use it."""
    if not secret:
        return ""
    return f"********{secret[-4:]}" if len(secret) > 4 else "********"


def model_view(cwd: Path) -> dict[str, Any]:
    """The model configuration, with the secrets taken out.

    Only the settings the settings page shows are here: the rest of the model
    lives in the configuration file, and the file is the only place it is read
    from.
    """
    config = load_config([], cwd=cwd)
    model = config.model
    kwargs = dict(model.model_kwargs)
    api_key = effective_api_key(cwd)
    resolved, alias = resolve_alias(model.litellm_config, model.model_name)
    base = str(model.api_base or kwargs.get("api_base") or alias.get("api_base") or "")
    provider = provider_of(resolved, base)
    own_key = model.api_key or kwargs.get("api_key") or alias.get("api_key")
    return {
        "model_name": model.model_name,
        "provider": provider,
        "api_base": str(model.api_base or kwargs.get("api_base") or ""),
        "api_key_set": bool(api_key),
        "api_key_hint": hint(api_key),
        "key_source": key_source(own_key, provider),
        "key_env": env_var(provider),
        "max_retries": model.max_retries,
    }


def user_config_path() -> Path:
    return config_home() / "config.yaml"


def _permission_of(layer: dict) -> dict:
    permissions = layer.get("permissions")
    return permissions if isinstance(permissions, dict) else {}


def _permission_source(layers: list[tuple[str, dict]], field: str) -> str:
    """The layer the setting comes from, the last one that defines it."""
    source = "defaults"
    for name, layer in layers:
        if field in _permission_of(layer):
            source = name
    return source


def permissions_view(cwd: Path, *, server_mode: str = "") -> dict[str, Any]:
    """The permission settings, as the browser sees them.

    `server_mode` is the mode the server was started with. It wins over the
    files, so it is what the page shows and what the user has to be told about.
    """
    layers = config_layers(cwd)
    permissions = load_config([], cwd=cwd).permissions
    source = {field: _permission_source(layers, field) for field in PERMISSION_FIELDS}
    if server_mode:
        source["mode"] = "server"
    return {
        "mode": server_mode or permissions.mode,
        "modes": list(PERMISSION_MODES),
        "deny_paths": list(permissions.deny_paths),
        "include_dirs": list(permissions.include_dirs),
        "network": permissions.network,
        "networks": list(NETWORK_POLICIES),
        "source": source,
        "server_mode": server_mode,
    }


def _default_model() -> dict[str, Any]:
    """The model settings of a fresh installation: the ones the user never wrote.

    A setting that is this one is not written to the user file: the shipped
    default may change, and a user who never touched the setting must get the
    new one.
    """
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8")) or {}
    return {**ModelConfig().model_dump(), **(defaults.get("model") or {})}


def _keep(model: dict, key: str, value: Any, default: Any) -> None:
    """Write a setting, or drop it when it is the default."""
    if value == default:
        model.pop(key, None)
    else:
        model[key] = value


def write_user_permissions(payload: dict) -> Path:
    """Merge the permission settings into the user level configuration file.

    The rules are not touched: they are edited by the approvals of the chat
    page, not here. A setting that is the shipped default is not written at
    all, so that a later change of the default reaches the user who never
    touched it.
    """
    path = user_config_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
    defaults = PermissionConfig().model_dump()

    mode = payload.get("mode")
    if isinstance(mode, str) and mode.strip():
        if mode.strip() not in PERMISSION_MODES:
            raise ValueError(f"unknown permission mode '{mode}'")
        _keep(permissions, "mode", mode.strip(), defaults["mode"])
    for field in ("deny_paths", "include_dirs"):
        values = payload.get(field)
        if isinstance(values, list):
            _keep(permissions, field, [str(value).strip() for value in values if str(value).strip()], defaults[field])
    network = payload.get("network")
    if isinstance(network, str) and network.strip():
        if network.strip() not in NETWORK_POLICIES:
            raise ValueError(f"unknown network policy '{network}'")
        _keep(permissions, "network", network.strip(), defaults["network"])

    if permissions:
        data["permissions"] = permissions
    else:
        data.pop("permissions", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def write_user_model(payload: dict) -> Path:
    """Merge the model settings into the user level configuration file.

    The project level file is never written: it is in the repository. The
    sections the page does not know about are kept as they are. A setting that
    is the shipped default is not written at all, so that a later change of the
    default reaches the user who never touched it.
    """
    path = user_config_path()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict):
        data = {}
    model = data.get("model")
    if not isinstance(model, dict):
        model = {}
    kwargs = model.get("model_kwargs")
    if not isinstance(kwargs, dict):
        kwargs = {}
    defaults = _default_model()

    for field in SECRET_FIELDS:
        """The key and the address have a field of their own now: the old place is left."""
        legacy = kwargs.pop(field, None)
        if legacy is not None:
            model.setdefault(field, legacy)

    name = payload.get("model_name")
    if isinstance(name, str):
        _keep(model, "model_name", name.strip(), defaults["model_name"])
    aliases = payload.get("litellm_config")
    if isinstance(aliases, str):
        _keep(model, "litellm_config", aliases.strip(), defaults["litellm_config"])
    base = payload.get("api_base")
    if isinstance(base, str):
        if base.strip():
            model["api_base"] = api_base_of(base)
        else:
            model.pop("api_base", None)
    key = payload.get("api_key")
    if isinstance(key, str):
        """An empty key removes it, a missing one keeps it."""
        if key.strip():
            model["api_key"] = key.strip()
        else:
            model.pop("api_key", None)
    if payload.get("max_retries") is not None:
        _keep(model, "max_retries", int(payload["max_retries"]), defaults["max_retries"])
    cache = payload.get("set_cache_control")
    if cache is not None:
        _keep(model, "set_cache_control", cache or None, defaults["set_cache_control"])
    effort = payload.get("reasoning_effort")
    if isinstance(effort, str):
        if effort.strip() and effort.strip() not in EFFORTS:
            raise ValueError(f"unknown reasoning effort '{effort}'")
        _keep(model, "reasoning_effort", effort.strip(), defaults["reasoning_effort"])
    verbosity = payload.get("verbosity")
    if isinstance(verbosity, str):
        if verbosity.strip() and verbosity.strip() not in VERBOSITIES:
            raise ValueError(f"unknown verbosity '{verbosity}'")
        _keep(model, "verbosity", verbosity.strip(), defaults["verbosity"])
    review = payload.get("review_model")
    if isinstance(review, str):
        _keep(model, "review_model", review.strip(), defaults["review_model"])
    routing = payload.get("routing")
    if isinstance(routing, dict):
        for purpose in routing:
            if purpose not in PURPOSES:
                raise ValueError(f"unknown purpose '{purpose}'. Use one of: {', '.join(PURPOSES)}.")
        _keep(model, "routing", {str(key): str(value) for key, value in routing.items()}, defaults["routing"])
    rules = payload.get("routing_rules")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, dict):
                check_routing_rule(rule)
        _keep(model, "routing_rules", [rule for rule in rules if isinstance(rule, dict)], defaults["routing_rules"])
    extra = payload.get("model_kwargs")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key in SECRET_FIELDS:
                continue
            kwargs[str(key)] = value
        check_reserved(kwargs)
        """The page may not write a file that breaks the agent: the agent refuses it at the start."""

    if kwargs:
        model["model_kwargs"] = kwargs
    else:
        model.pop("model_kwargs", None)
    if model:
        data["model"] = model
    else:
        data.pop("model", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


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


def effective_model(cwd: Path, overrides: dict) -> dict:
    """The model to talk to and the kwargs to talk with, with the overrides applied.

    An alias of a litellm config file is resolved here: the name becomes the
    model of the provider and the parameters of the alias are the kwargs.
    """
    config = load_config([], cwd=cwd)
    kwargs = dict(config.model.model_kwargs)
    if config.model.api_key:
        kwargs["api_key"] = config.model.api_key
        """The field of its own wins over the old place of `model_kwargs`."""
    if config.model.api_base:
        kwargs["api_base"] = config.model.api_base
    name = config.model.model_name
    aliases = config.model.litellm_config
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
        "reasoning_effort": config.model.reasoning_effort,
    }


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


def check_litellm_config(path: str, name: str = "") -> dict[str, Any]:
    """The file of the aliases: does it exist, does it parse, what is in it."""
    if not path:
        return {"ok": True, "path": "", "aliases": [], "error": ""}
    file = locate(path)
    if not file.is_file():
        return {"ok": False, "path": str(file), "aliases": [], "error": "the file does not exist"}
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        return {"ok": False, "path": str(file), "aliases": [], "error": f"the file is not valid YAML: {error}"}
    if not isinstance(data, dict) or not isinstance(data.get("model_list"), list):
        return {"ok": False, "path": str(file), "aliases": [], "error": "the file has no model_list"}
    aliases = [
        entry.get("model_name") for entry in data["model_list"] if isinstance(entry, dict) and entry.get("model_name")
    ]
    if name and name not in aliases:
        return {
            "ok": False,
            "path": str(file),
            "aliases": aliases,
            "error": f"'{name}' is not one of the aliases of this file",
        }
    return {"ok": True, "path": str(file), "aliases": aliases, "error": ""}


def check_tools(backend) -> dict[str, Any]:
    """The model has to call the tools, or the agent cannot work at all."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Answer with a ping.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    try:
        message = backend.query([{"role": "user", "content": "Call the ping tool."}], tools=tools, max_tokens=64)
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    calls = message.get("tool_calls") or []
    return {
        "ok": bool(calls),
        "error": "" if calls else "the model did not call the tool",
        "calls": len(calls),
    }


def test_connection(effective: dict) -> dict[str, Any]:
    """See whether the settings work: the file, the call and the tools."""
    from coderagent.models.backends import LiteLLMBackend

    name = effective["model_name"]
    kwargs = effective["model_kwargs"]
    base = str(kwargs.get("api_base") or "")
    provider = effective.get("provider") or provider_of(name, base)
    key = key_of(effective)
    """The key of the environment counts too: the call below uses it."""
    report: dict[str, Any] = {
        "ok": False,
        "resolved": {
            "model_name": name,
            "provider": provider,
            "alias": effective.get("alias", ""),
            "api_base": base,
            "api_key_set": bool(key),
            "api_key_hint": hint(key),
            "key_source": key_source(str(kwargs.get("api_key") or ""), provider),
            "key_env": env_var(provider),
        },
        "file": check_litellm_config(effective.get("litellm_config", ""), effective.get("requested", "")),
    }
    """A wrong key should fail right away, not after ten tries."""
    started = time.time()
    try:
        backend = LiteLLMBackend(
            name,
            model_kwargs=kwargs,
            reasoning_effort=effective.get("reasoning_effort", ""),
            max_retries=1,
        )
        message = backend.query([{"role": "user", "content": "ping"}], max_tokens=1)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        return report
    extra = message.get("extra") or {}
    report.update(
        {
            "ok": True,
            "content": str(message.get("content", ""))[:200],
            "cost": float(extra.get("cost") or 0.0),
            "latency_ms": int((time.time() - started) * 1000),
            "tools": check_tools(backend),
        }
    )
    return report
