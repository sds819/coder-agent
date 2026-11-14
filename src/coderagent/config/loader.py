"""Configuration loading: built-in defaults, project file, user file, CLI overrides."""

import os
from pathlib import Path

import yaml

from coderagent.config.schema import Config
from coderagent.core.trust import waiting, without_untrusted
from coderagent.paths import config_home
from minisweagent.config import get_config_from_spec
from minisweagent.utils.serialize import recursive_merge

DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"
PROJECT_CONFIG = Path(".coderagent") / "config.yaml"
DEFAULT_MODEL_NAME = "anthropic/claude-sonnet-4-5"


def config_layers(cwd: Path | None = None) -> list[tuple[str, dict]]:
    """The configuration layers, from the lowest to the highest priority.

    The project layer is the one of the repository the agent works in. The code
    it defines runs without asking the user, so it waits for a decision of the
    user and is not in the layer until it is trusted.
    """
    directory = Path(cwd) if cwd else Path.cwd()
    layers = [("defaults", _read(DEFAULTS_PATH))]
    project = _project_config_path(directory)
    if project.exists():
        layers.append(("project", without_untrusted(_read(project), directory)))
    user = config_home() / "config.yaml"
    if user.exists():
        layers.append(("user", _read(user)))
    return layers


def pending_code(cwd: Path | None = None, user_home: Path | None = None) -> dict[str, str]:
    """The code of the project that waits for a decision of the user."""
    directory = Path(cwd) if cwd else Path.cwd()
    project = _project_config_path(directory)
    if not project.exists():
        return {}
    return waiting(_read(project), directory, user_home)


def load_config(specs: list[str] | None = None, cwd: Path | None = None) -> Config:
    """Merge the four configuration layers, later layers win."""
    layers = [data for _, data in config_layers(cwd)]
    layers.extend(get_config_from_spec(spec) for spec in specs or [])
    merged = recursive_merge(*layers)
    model = merged.setdefault("model", {})
    model["model_name"] = model.get("model_name") or os.getenv("MSWEA_MODEL_NAME") or DEFAULT_MODEL_NAME
    return Config(**merged)


def _read(path: Path) -> dict:
    """A configuration file as a mapping. A file that is not there is empty."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _project_config_path(cwd: Path | None = None) -> Path:
    return (Path(cwd) if cwd else Path.cwd()) / PROJECT_CONFIG
