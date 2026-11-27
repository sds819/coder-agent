"""The permission settings, as the browser sees them.

The settings of the model have their own modules now: `coderagent.models.settings`
holds them, `coderagent.config.writer` writes them and `coderagent.models.check`
tries them out.
"""

from pathlib import Path
from typing import Any

from coderagent.config.loader import config_layers, load_config
from coderagent.config.writer import NETWORK_POLICIES, PERMISSION_FIELDS, PERMISSION_MODES
from coderagent.models.provider import PROVIDERS

ENV_KEYS = PROVIDERS
"""The environment variable of the key of a provider. The name of the model says which provider it is."""


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
