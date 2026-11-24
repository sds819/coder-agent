"""Browsing the working directory from the browser.

The paths the browser asks for have to stay inside the working directory. The
rules of the user cannot widen that, so the check is done here with
`within_bounds` and not through `evaluate`, which judges whether a call is
allowed rather than whether a path is in range.

The panel of the files lists the directories the user opened to the agent
(`permissions.include_dirs`) and nothing else. Without them the working
directory is the one.
"""

import subprocess
from pathlib import Path
from typing import Any

from coderagent.config.schema import Config
from coderagent.core.events import EventBus
from coderagent.core.session import Session
from coderagent.tools.base import ToolContext
from coderagent.tools.builtin.fs import ReadTool
from coderagent.tools.builtin.search import list_entries
from coderagent.tools.permissions import PermissionPolicy


class OutsideBounds(ValueError):
    """The path is not in the working directory."""


def policy_for(config: Config, cwd: Path) -> PermissionPolicy:
    """The policy of the boundaries. The rules are not part of it."""
    return PermissionPolicy(
        config.permissions.mode,
        [],
        cwd=cwd,
        include_dirs=config.permissions.include_dirs,
        deny_paths=config.permissions.deny_paths,
    )


def resolve(cwd: Path, path: str, policy: PermissionPolicy) -> Path:
    """The absolute path of a file of the working directory."""
    target = Path(path or ".")
    resolved = (target if target.is_absolute() else cwd / target).resolve()
    if not policy.within_bounds(str(resolved)):
        raise OutsideBounds(f"'{path}' is outside the working directory {policy.cwd}")
    denied = policy.denied_path(str(resolved))
    if denied:
        raise OutsideBounds(f"'{path}' is denied by the configuration ('{denied}')")
    return resolved


def listing(cwd: Path, path: str, depth: int, policy: PermissionPolicy) -> tuple[str, list[dict[str, Any]]]:
    """The directory that is listed and the entries of it.

    Only the directories that are open may be listed: the other files and
    directories of the disk are not shown to the browser.
    """
    directories = policy.roots()
    if not path or path == ".":
        if len(directories) == 1:
            return _entries(directories[0], depth)
        return "", [_entry(directory, True) for directory in directories]
    target = resolve(cwd, path, policy)
    if not any(target == directory or target.is_relative_to(directory) for directory in directories):
        raise OutsideBounds(
            f"'{path}' is not in the directories that are open: {', '.join(str(d) for d in directories)}"
        )
    return _entries(target, depth)


def _entries(target: Path, depth: int) -> tuple[str, list[dict[str, Any]]]:
    """The entries of a directory, one level or the whole tree."""
    if not target.is_dir():
        raise NotADirectoryError(f"'{target}' is not a directory")
    entries = []
    for absolute, kind in list_entries(target, depth):
        entries.append(_entry(absolute, kind == "d"))
    return target.as_posix(), entries


def _entry(absolute: Path, is_dir: bool) -> dict[str, Any]:
    """One entry of the list. The path is absolute: the browser sends it back."""
    return {
        "path": absolute.as_posix(),
        "name": absolute.name,
        "is_dir": is_dir,
        "size": absolute.stat().st_size if not is_dir else 0,
    }


def read(cwd: Path, path: str, policy: PermissionPolicy, config: Config) -> dict[str, Any]:
    """The content of a file, with the line numbers the agent gets to see."""
    target = resolve(cwd, path, policy)
    context = ToolContext(
        cwd=cwd,
        session=Session(id="web", cwd=cwd, created_at=0.0, updated_at=0.0),
        bus=EventBus(),
        policy=policy,
        config=config.tools,
    )
    result = ReadTool().run({"path": str(target)}, context)
    return {"path": str(target), "content": result.content, "is_error": result.is_error}


def diff(cwd: Path, path: str, policy: PermissionPolicy) -> str:
    """The changes of the working tree for a path."""
    target = resolve(cwd, path, policy)
    if not target.is_relative_to(cwd):
        """The file is not in the working tree: it has no diff."""
        return ""
    result = subprocess.run(["git", "diff", "--", str(target)], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return result.stderr.strip() or f"git diff failed with code {result.returncode}"
    return result.stdout
