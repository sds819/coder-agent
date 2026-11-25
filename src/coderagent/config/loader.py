"""Configuration loading: built-in defaults, project file, user file, CLI overrides."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from coderagent.config.schema import Config
from coderagent.core.os_sandbox import FULL_ACCESS, MODES
from coderagent.core.trust import tightened, waiting, without_untrusted
from coderagent.paths import config_home
from minisweagent.config import get_config_from_spec
from minisweagent.utils.serialize import recursive_merge

DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"
PROJECT_CONFIG = Path(".coderagent") / "config.yaml"
DEFAULT_MODEL_NAME = "anthropic/claude-sonnet-4-5"
ADDED_LISTS = (
    ("permissions", "rules"),
    ("permissions", "deny_paths"),
    ("tools", "disabled"),
    ("shell_environment", "exclude"),
)
"""The lists that every layer adds to, instead of replacing."""

LIMIT_KEYS = (
    ("agent", "max_turns"),
    ("agent", "cost_limit"),
    ("agent", "token_limit"),
    ("agent", "subagent_max_turns"),
    ("agent", "subagent_max_parallel"),
    ("tools", "bash_timeout"),
    ("tools", "max_output_tokens"),
)
"""The ceilings of a session. A project may lower them, never raise them."""

UNLIMITED = {"max_turns", "cost_limit", "token_limit", "subagent_max_turns", "subagent_max_parallel"}
"""The ceilings where zero means: no ceiling at all."""


def config_layers(cwd: Path | None = None) -> list[tuple[str, dict]]:
    """The configuration layers, from the lowest to the highest priority.

    The project layer is the one of the repository the agent works in. The code
    it defines runs without asking the user, so it waits for a decision of the
    user and is not in the layer until it is trusted. What it may not do is
    loosen the permissions: it may take tools away, never give them.
    """
    directory = Path(cwd) if cwd else Path.cwd()
    layers = [("defaults", _read(DEFAULTS_PATH))]
    project = _project_config_path(directory)
    if project.exists():
        layers.append(("project", _sanitized(tightened(without_untrusted(_read(project), directory)))))
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
    """Merge the four configuration layers, later layers win.

    The project may only take tools away: the rules and the paths it denies
    are added to the ones of the user, and the tools it names may only remove
    from the tools of the others.

    """
    layers = config_layers(cwd)
    spec_layers = [get_config_from_spec(spec) for spec in specs or []]
    project = next((data for name, data in layers if name == "project"), None)
    defaults = next((data for name, data in layers if name == "defaults"), {})
    user = next((data for name, data in layers if name == "user"), {})
    profile = _profile(recursive_merge(*[data for _, data in layers], *spec_layers))
    base = recursive_merge(*[data for name, data in layers if name != "project"], profile, *spec_layers)
    merged = recursive_merge(*[data for _, data in layers], profile, *spec_layers)
    if project is not None:
        for path in ADDED_LISTS:
            _put(merged, path, [*_items(project, path), *_items(base, path)])
        if isinstance(project.get("tools"), dict) and "enabled" in project["tools"]:
            enabled = _items(project, ("tools", "enabled"))
            _put(merged, ("tools", "enabled"), [tool for tool in _items(base, ("tools", "enabled")) if tool in enabled])
        project_permissions = project.get("permissions")
        if isinstance(project_permissions, dict) and project_permissions.get("network") == "deny":
            """A project may close the network: the user does not open it again."""
            merged.setdefault("permissions", {})["network"] = "deny"
        _tighten_sandbox(merged, project)
        _tighten_telemetry(merged, project)
        _tighten_limits(merged, defaults, user, recursive_merge(profile, *spec_layers), project)
        merged.setdefault("model", {})["capabilities"] = base.get("model", {}).get("capabilities", {})
        """A project does not say what the model of the user takes."""
    model = merged.setdefault("model", {})
    model["model_name"] = model.get("model_name") or os.getenv("MSWEA_MODEL_NAME") or DEFAULT_MODEL_NAME
    return Config(**merged)


def problems(error: ValidationError) -> str:
    """What is wrong with the configuration, one thing per problem.

    The error of pydantic is meant for a program: this is meant for a person.
    """
    return "; ".join(
        f"{'.'.join(str(part) for part in entry['loc'])}: {entry['msg'].removeprefix('Value error, ')}"
        for entry in error.errors()
    )


def _sanitized(project: dict) -> dict:
    """The project without the values that the schema would refuse.

    A project may not break the session of the user: a value that is not
    understood is left out, and the rest of the project is kept. The mistake
    of a project is a warning, not the end of the session.
    """
    result = {}
    for key, value in project.items():
        model = _model_of(key)
        if model is not None and isinstance(value, dict):
            value = _accepted(model, value)
        result[key] = value
    return _accepted(Config, result)


def _model_of(key: str) -> type[BaseModel] | None:
    """The model of a section of the configuration, when it has one."""
    field = Config.model_fields.get(key)
    annotation = field.annotation if field else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _accepted(model: type[BaseModel], values: dict) -> dict:
    """The values of a mapping that the model accepts.

    A value that the model would refuse is left out, one key at a time: the
    rest of the section is still worth something.
    """
    kept = dict(values)
    while kept:
        try:
            model(**kept)
            return kept
        except ValidationError as error:
            keys = {str(entry["loc"][0]) for entry in error.errors() if entry.get("loc")}
            if not keys:
                return {}
            for key in keys:
                kept.pop(key, None)
    return {}


def _tighten_telemetry(merged: dict, project: dict) -> None:
    """A project may close the trace, and the user does not open it again.

    The trace of a session holds what the agent read. Where it goes is the
    decision of the user: a project may say "do not send it", never "send it
    to me".
    """
    telemetry = project.get("telemetry")
    if isinstance(telemetry, dict) and "otel_endpoint" in telemetry:
        merged.setdefault("telemetry", {})["otel_endpoint"] = ""


def _profile(merged: dict) -> dict:
    """The configuration of the profile that is in effect.

    The name of the profile comes from the user or from the command line: a
    project may neither define a profile nor choose one, because choosing a set
    of permissions is the decision of the user.
    """
    tables = merged.get("profiles")
    tables = tables if isinstance(tables, dict) else {}
    name = str(merged.get("profile") or "")
    if not name:
        return {}
    chosen = tables.get(name)
    if not isinstance(chosen, dict):
        raise ValueError(f"unknown profile '{name}'. Use one of: {', '.join(sorted(tables)) or 'none'}.")
    return chosen


def _tighten_limits(merged: dict, defaults: dict, user: dict, explicit: dict, project: dict) -> None:
    """The ceilings of a session belong to the user: a project may lower them.

    A ceiling that the user names — in the file of the user, in a profile or on
    the command line — is the last word. A project that asks for a higher one
    than the default is given the default instead.
    """
    for section, key in LIMIT_KEYS:
        value = _number(project, section, key)
        if value is None:
            continue
        if _number(user, section, key) is not None or _number(explicit, section, key) is not None:
            continue
        reference = _number(defaults, section, key)
        if reference is None:
            continue
        merged.setdefault(section, {})[key] = value if _lower(value, reference, key) else reference


def _number(layer: dict, section: str, key: str) -> float | None:
    """The number at a path of a layer, when there is one there."""
    value = (layer.get(section) or {}).get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _lower(value: float, reference: float, key: str) -> bool:
    """Whether the ceiling of the project is the lower one."""
    if key in UNLIMITED:
        if value == 0:
            """No ceiling at all is not a lower ceiling."""
            return False
        if reference == 0:
            return True
    return value < reference


def _tighten_sandbox(merged: dict, project: dict) -> None:
    """A project may close the sandbox, and the user does not open it again.

    The tightest of the two wins: a project that says `read-only` keeps the
    agent from writing, whatever the user level says.
    """
    mode = str((project.get("sandbox") or {}).get("mode") or "")
    current = str((merged.get("sandbox") or {}).get("mode") or FULL_ACCESS)
    if current not in MODES:
        current = FULL_ACCESS
    if mode in MODES and MODES.index(mode) < MODES.index(current):
        merged.setdefault("sandbox", {})["mode"] = mode


def _items(layer: dict, path: tuple[str, ...]) -> list:
    """The list at a path of a layer. A path that is not there is empty."""
    value: object = layer
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, list) else []


def _put(merged: dict, path: tuple[str, ...], value: list) -> None:
    """Write a list into a path of the merged configuration."""
    target = merged
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def _read(path: Path) -> dict:
    """A configuration file as a mapping. A file that is not there is empty."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _project_config_path(cwd: Path | None = None) -> Path:
    return (Path(cwd) if cwd else Path.cwd()) / PROJECT_CONFIG
