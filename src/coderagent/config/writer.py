"""Writing the user level configuration file.

The project level file is never written: it is in the repository. The writing
never calls the model: a configuration that does not work yet is worth writing
down, to be fixed later.
"""

from pathlib import Path
from typing import Any

import yaml

from coderagent.config.loader import DEFAULTS_PATH
from coderagent.config.schema import PURPOSES, ModelConfig, PermissionConfig, check_routing_rule
from coderagent.models.call import check_reserved
from coderagent.models.reasoning import EFFORTS
from coderagent.models.settings import api_base_of
from coderagent.models.verbosity import VERBOSITIES
from coderagent.paths import config_home
from coderagent.tools.permissions import NETWORK_POLICIES, PermissionMode

PERMISSION_MODES = [mode.value for mode in PermissionMode]
"""The permission modes the browser can choose from."""

PERMISSION_FIELDS = ("mode", "deny_paths", "include_dirs", "network")
"""The permission settings that live directly under `permissions:`."""

SECRET_FIELDS = ("api_base", "api_key")
"""The settings of the model that have a field of their own, next to `model_kwargs`."""


def user_config_path() -> Path:
    """The configuration file of the user."""
    return config_home() / "config.yaml"


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
