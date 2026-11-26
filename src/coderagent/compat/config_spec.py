"""The configuration files of the agent and the `key=value` overrides of the command line."""

import json
import os
from pathlib import Path

import yaml

builtin_config_dir = Path(__file__).parent.parent / "config"
"""The configuration files that come with the package."""


def get_config_path(config_spec: str | Path) -> Path:
    """The path of a configuration file."""
    config_spec = Path(config_spec)
    if config_spec.suffix != ".yaml":
        config_spec = config_spec.with_suffix(".yaml")
    candidates = [
        Path(config_spec),
        Path(os.getenv("MSWEA_CONFIG_DIR", ".")) / config_spec,
        builtin_config_dir / config_spec,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Could not find config file for {config_spec} (tried: {candidates})")


def _key_value_spec_to_nested_dict(config_spec: str) -> dict:
    """The `key=value` of the command line as a dictionary.

    Example:

    "model.model_name=anthropic/claude-sonnet-4-5-20250929"   ->
    {"model": {"model_name": "anthropic/claude-sonnet-4-5-20250929"}}
    """
    key, value = config_spec.split("=", 1)
    try:
        value = json.loads(value)
    except json.JSONDecodeError:
        pass
    keys = key.split(".")
    if any(k == "" for k in keys):
        raise ValueError(f"Invalid config spec {config_spec!r}: empty config key")
    result = {}
    current = result
    for k in keys[:-1]:
        current[k] = {}
        current = current[k]
    current[keys[-1]] = value
    return result


def get_config_from_spec(config_spec: str | Path) -> dict:
    """The configuration of a spec: a file or a `key=value`."""
    if isinstance(config_spec, str) and "=" in config_spec:
        return _key_value_spec_to_nested_dict(config_spec)
    path = get_config_path(config_spec)
    return yaml.safe_load(path.read_text(encoding="utf-8"))
