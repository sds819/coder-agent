"""The model list of a litellm config file: the aliases of the models."""

import logging
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from coderagent.paths import config_home

logger = logging.getLogger("coderagent.models.litellm_config")


def locate(path: str | Path) -> Path:
    """The file of the aliases.

    A relative path is looked for in the home of the user first and in the
    working directory after it: the setting lives in a file that does not move,
    the working directory does.
    """
    file = Path(path).expanduser()
    if file.is_absolute():
        return file
    for candidate in (config_home() / file, Path.cwd() / file):
        if candidate.exists():
            return candidate
    """The file that is not there: the home of the user is the place to look for it."""
    return config_home() / file


def deployments(path: str | Path) -> dict[str, dict[str, Any]]:
    """The model list of the file, keyed by the alias of every entry."""
    if not path:
        return {}
    file = locate(path)
    if not file.is_file():
        return {}
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    return {
        entry["model_name"]: entry.get("litellm_params") or {}
        for entry in data.get("model_list") or []
        if entry.get("model_name")
    }


@cache
def _warn_about_the_alias(path: str, name: str, aliases: tuple[str, ...]) -> None:
    """The file of the aliases does not have this name: it is of no use."""
    logger.warning(
        "The model '%s' is not one of the aliases of %s (%s): the settings of that file are not used.",
        name,
        path,
        ", ".join(aliases),
    )


def resolve(path: str | Path, model_name: str) -> tuple[str, dict[str, Any]]:
    """The real model and the parameters of an alias.

    The name itself and no parameters when the name is not an alias.
    """
    entries = deployments(path)
    params = entries.get(model_name)
    if params is None:
        if entries:
            """The file has models, but not this one: the file is of no use for it."""
            _warn_about_the_alias(str(locate(path)), model_name, tuple(entries))
        return model_name, {}
    return params.get("model", model_name), {key: value for key, value in params.items() if key != "model"}
