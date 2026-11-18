"""The model configuration as the browser sees it: merged, layered and without secrets.

The api key is only ever written to the user level configuration file, and it
never leaves the server in clear text.
"""

import contextlib
import io
import os
import time
from pathlib import Path
from typing import Any

import yaml
from litellm.utils import get_llm_provider

from coderagent.config.loader import DEFAULTS_PATH, config_layers, load_config
from coderagent.config.schema import ModelConfig, PermissionConfig
from coderagent.models.litellm_config import resolve as resolve_alias
from coderagent.models.reasoning import EFFORTS
from coderagent.models.verbosity import VERBOSITIES
from coderagent.paths import config_home
from coderagent.tools.permissions import PermissionMode

SECRET_MARKERS = ("key", "token", "secret", "password")
"""The names of the settings that never leave the server in clear text."""

PERMISSION_MODES = [mode.value for mode in PermissionMode]
"""The permission modes the browser can choose from."""

PERMISSION_FIELDS = ("mode", "deny_paths", "include_dirs", "network")
"""The permission settings that live directly under `permissions:`."""

NETWORK_POLICIES = ("allow", "deny")
"""What the browser may choose for the network."""

DIRECT_FIELDS = (
    "model_name",
    "max_retries",
    "set_cache_control",
    "routing",
    "routing_rules",
    "litellm_config",
    "reasoning_effort",
    "verbosity",
    "review_model",
)
"""The settings of the model that live directly under `model:`."""

MODEL_FIELDS = (*DIRECT_FIELDS, "api_base", "api_key")
"""The settings the configuration page shows."""

ENV_KEYS = {
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
}
"""The environment variable of the key of a provider. The name of the model says which provider it is."""


def is_secret(name: str) -> bool:
    return any(marker in name.lower() for marker in SECRET_MARKERS)


def redact(value: Any) -> Any:
    """Everything that looks like a secret is replaced by a mask."""
    if isinstance(value, dict):
        return {key: ("***" if is_secret(str(key)) else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def hint(secret: str) -> str:
    """A hint of a secret: enough to recognize it, too little to use it."""
    if not secret:
        return ""
    return f"********{secret[-4:]}" if len(secret) > 4 else "********"


def _model_of(layer: dict) -> dict:
    model = layer.get("model")
    return model if isinstance(model, dict) else {}


def _defines(layer: dict, field: str) -> bool:
    model = _model_of(layer)
    if field in DIRECT_FIELDS:
        return field in model
    kwargs = model.get("model_kwargs")
    return isinstance(kwargs, dict) and field in kwargs


def sources(cwd: Path) -> dict[str, str]:
    """Which layer every model setting comes from.

    The files win over the environment, the same way the loader merges them.
    """
    layers = config_layers(cwd)
    merged = load_config([], cwd=cwd)
    name, _ = resolve_alias(merged.model.litellm_config, merged.model.model_name)
    result = {}
    for field in (*MODEL_FIELDS, *merged.model.model_kwargs):
        source = "defaults"
        for name_of_layer, layer in layers:
            if _defines(layer, field):
                source = name_of_layer
        if source == "defaults" and field == "model_name" and os.getenv("MSWEA_MODEL_NAME"):
            source = "env"
        if source == "defaults" and field == "api_key" and env_api_key(name):
            source = "env"
        result[field] = source
    return result


def model_view(cwd: Path) -> dict[str, Any]:
    """The model configuration, with the secrets taken out."""
    config = load_config([], cwd=cwd)
    model = config.model
    kwargs = dict(model.model_kwargs)
    api_key = effective_api_key(cwd)
    return {
        "model_name": model.model_name,
        "litellm_config": model.litellm_config,
        "api_base": str(kwargs.get("api_base") or ""),
        "api_key_set": bool(api_key),
        "api_key_hint": hint(api_key),
        "max_retries": model.max_retries,
        "set_cache_control": model.set_cache_control or "",
        "reasoning_effort": model.reasoning_effort,
        "efforts": list(EFFORTS),
        "verbosity": model.verbosity,
        "verbosities": list(VERBOSITIES),
        "review_model": model.review_model,
        "routing": model.routing,
        "routing_rules": [rule.model_dump() for rule in model.routing_rules],
        "model_kwargs": {key: value for key, value in kwargs.items() if not is_secret(key)},
    }


def layers_preview(cwd: Path) -> list[dict[str, Any]]:
    """Every layer, with the secrets taken out."""
    return [{"layer": name, "model": redact(_model_of(layer))} for name, layer in config_layers(cwd)]


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

    name = payload.get("model_name")
    if isinstance(name, str):
        _keep(model, "model_name", name.strip(), defaults["model_name"])
    aliases = payload.get("litellm_config")
    if isinstance(aliases, str):
        _keep(model, "litellm_config", aliases.strip(), defaults["litellm_config"])
    base = payload.get("api_base")
    if isinstance(base, str):
        if base.strip():
            kwargs["api_base"] = api_base_of(base)
        else:
            kwargs.pop("api_base", None)
    key = payload.get("api_key")
    if isinstance(key, str):
        """An empty key removes it, a missing one keeps it."""
        if key.strip():
            kwargs["api_key"] = key.strip()
        else:
            kwargs.pop("api_key", None)
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
        _keep(model, "routing", {str(key): str(value) for key, value in routing.items()}, defaults["routing"])
    rules = payload.get("routing_rules")
    if isinstance(rules, list):
        _keep(model, "routing_rules", [rule for rule in rules if isinstance(rule, dict)], defaults["routing_rules"])
    extra = payload.get("model_kwargs")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key in ("api_key", "api_base"):
                continue
            kwargs[str(key)] = value

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
    return {
        "model_name": resolved,
        "requested": name,
        "alias": name if resolved != name else "",
        "litellm_config": aliases,
        "model_kwargs": params | kwargs,
        "reasoning_effort": config.model.reasoning_effort,
    }


def provider_of(model_name: str) -> str:
    """The provider of a model: the part before the slash, or what litellm makes of the name."""
    if "/" in model_name:
        return model_name.split("/", 1)[0].lower()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            _, provider, _, _ = get_llm_provider(model=model_name)
    except Exception:
        return ""
    return provider


def env_api_key(model_name: str) -> str:
    """The key the environment has for the provider of the model."""
    return os.getenv(ENV_KEYS.get(provider_of(model_name), ""), "")


def effective_api_key(cwd: Path) -> str:
    """The key the agent would use: the one of the settings, the one of the alias or the one of the environment."""
    config = load_config([], cwd=cwd)
    name, params = resolve_alias(config.model.litellm_config, config.model.model_name)
    key = config.model.model_kwargs.get("api_key") or params.get("api_key") or env_api_key(name)
    return str(key or "")


def check_litellm_config(path: str, name: str = "") -> dict[str, Any]:
    """The file of the aliases: does it exist, does it parse, what is in it."""
    if not path:
        return {"ok": True, "path": "", "aliases": [], "error": ""}
    file = Path(path).expanduser()
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
    key = str(kwargs.get("api_key") or "")
    report: dict[str, Any] = {
        "ok": False,
        "resolved": {
            "model_name": name,
            "alias": effective.get("alias", ""),
            "api_base": str(kwargs.get("api_base") or ""),
            "api_key_set": bool(key),
            "api_key_hint": hint(key),
        },
        "file": check_litellm_config(effective.get("litellm_config", ""), effective.get("requested", "")),
    }
    backend = LiteLLMBackend(
        name,
        model_kwargs=kwargs,
        reasoning_effort=effective.get("reasoning_effort", ""),
        max_retries=1,
    )
    """A wrong key should fail right away, not after ten tries."""
    started = time.time()
    try:
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
