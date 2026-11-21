"""Putting a skill on the disk: the staging, the install and the lock file.

A skill that comes from the network waits before it is used. It is downloaded
into a staging directory, the user is shown what it is, and only then it is
moved into the directory the agent reads. What was installed, and where it
came from, is written into a lock file.
"""

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from coderagent.paths import config_home
from coderagent.skills import SKILL_FILE, SKILLS_DIR, parse_skill
from coderagent.skills.errors import SkillError
from coderagent.skills.sandbox import (
    SKILL_NAME,
    FileEntry,
    Policy,
    check_name,
    copy_tree,
    digest,
    entries_of,
    sanitize,
)
from coderagent.skills.source import Source, fetch, source_of

LOCK_FILE = "skills.lock.json"
"""The file that says what was installed here, and where it came from."""

CACHE_DIR = "cache/skills"
"""Where a download waits for the user to look at it."""

STAGE_FILE = "stage.json"
"""What is known about a staged skill."""

STAGE_LIFE = 30 * 60
"""The seconds a staged skill waits. After that it is of no use to anybody."""

SCRIPTS = (".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".bat", ".ps1")
"""The files the model may run with `bash`."""


@dataclass
class Staged:
    """A skill that waits for the user to say yes."""

    stage_id: str
    source: Source
    name: str
    description: str
    body: str
    files: list[FileEntry]
    sha256: str
    warnings: list[str] = field(default_factory=list)
    directory: Path = Path()
    """The directory of the skill. The scripts of the skill live in it."""


@dataclass
class Installed:
    """What the lock file knows about an installed skill."""

    name: str
    source: Source
    sha256: str
    installed_at: str
    files: list[FileEntry] = field(default_factory=list)


def stage(source: Source, policy: Policy, user_home: Path | None = None, token: str = "") -> Staged:
    """Download a skill and wait for the user to look at it.

    Nothing is put into the directory of the agent: the skill waits in the
    cache until the user says yes.
    """
    home = Path(user_home) if user_home else config_home()
    _clear_old_stages(home)
    stage_id = uuid.uuid4().hex
    workdir = home / CACHE_DIR / stage_id
    workdir.mkdir(parents=True, exist_ok=True)
    done = False
    try:
        fetched = fetch(source, workdir, policy, token=token)
        directory = workdir / "skill"
        if fetched.is_file():
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fetched, directory / SKILL_FILE)
            files = entries_of(directory)
        else:
            files = copy_tree(fetched, directory, policy)
        skill = parse_skill(directory / SKILL_FILE)
        if skill is None:
            raise SkillError("there is no SKILL.md in it")
        name, warnings = _name(skill, source, files)
        staged = Staged(
            stage_id=stage_id,
            source=source,
            name=name,
            description=skill.description,
            body=skill.body,
            files=files,
            sha256=digest(files),
            warnings=warnings,
            directory=directory,
        )
        _write_stage(staged, workdir)
        done = True
        return staged
    finally:
        if not done:
            shutil.rmtree(workdir, ignore_errors=True)


def read_stage(stage_id: str, user_home: Path | None = None) -> Staged:
    """A staged skill that is still waiting."""
    home = Path(user_home) if user_home else config_home()
    workdir = home / CACHE_DIR / stage_id
    path = workdir / STAGE_FILE
    if not path.exists():
        raise SkillError("the preview is gone, download it again")
    data = _read_json(path)
    directory = workdir / "skill"
    skill = parse_skill(directory / SKILL_FILE)
    return Staged(
        stage_id=stage_id,
        source=source_of(data.get("source") or {}),
        name=str(data.get("name") or ""),
        description=str(data.get("description") or ""),
        body=skill.body if skill else "",
        files=[
            FileEntry(str(item.get("path") or ""), int(item.get("size") or 0), str(item.get("sha256") or ""))
            for item in data.get("files") or []
        ],
        sha256=str(data.get("sha256") or ""),
        warnings=[str(warning) for warning in data.get("warnings") or []],
        directory=directory,
    )


def install(staged: Staged, user_home: Path | None = None, force: bool = False) -> Installed:
    """Put a staged skill where the agent finds it.

    A skill that is installed already is not replaced, unless the caller says
    that it means it.
    """
    home = Path(user_home) if user_home else config_home()
    skills = home / SKILLS_DIR
    target = skills / staged.name
    if target.exists():
        if not force:
            raise SkillError(f"'{staged.name}' is installed already")
        shutil.rmtree(target)
    skills.mkdir(parents=True, exist_ok=True)
    temporary = skills / f".{staged.name}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    shutil.copytree(staged.directory, temporary)
    temporary.rename(target)
    installed = Installed(
        name=staged.name,
        source=staged.source,
        sha256=staged.sha256,
        installed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        files=staged.files,
    )
    lock = read_lock(user_home)
    lock[staged.name] = installed
    write_lock(lock, user_home)
    shutil.rmtree(staged.directory.parent, ignore_errors=True)
    return installed


def check_update(installed: Installed, policy: Policy, user_home: Path | None = None, token: str = "") -> Staged | None:
    """The new version of an installed skill, when the source has one.

    Nothing when the source still says the same thing: the digest of the
    content is the same.
    """
    staged = stage(installed.source, policy, user_home, token)
    if staged.sha256 == installed.sha256:
        shutil.rmtree(staged.directory.parent, ignore_errors=True)
        return None
    return staged


def uninstall(name: str, user_home: Path | None = None) -> None:
    """Remove a skill that was installed here.

    A skill the user put there himself is not ours to remove.
    """
    home = Path(user_home) if user_home else config_home()
    lock = read_lock(user_home)
    if name not in lock:
        raise SkillError(f"'{name}' was not installed here, it is yours")
    shutil.rmtree(home / SKILLS_DIR / name)
    lock.pop(name)
    write_lock(lock, user_home)


def read_lock(user_home: Path | None = None) -> dict[str, Installed]:
    """The skills that were installed here."""
    path = lock_path(user_home)
    if not path.exists():
        return {}
    data = _read_json(path)
    skills = data.get("skills") if isinstance(data, dict) else {}
    result = {}
    for name, item in (skills or {}).items():
        installed = _installed(name, item)
        if installed is not None:
            result[name] = installed
    return result


def write_lock(skills: dict[str, Installed], user_home: Path | None = None) -> Path:
    """Write the lock file."""
    path = lock_path(user_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "skills": {
            name: {
                "source": item.source.as_dict(),
                "sha256": item.sha256,
                "installed_at": item.installed_at,
                "files": [{"path": entry.path, "size": entry.size, "sha256": entry.sha256} for entry in item.files],
            }
            for name, item in skills.items()
        },
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def lock_path(user_home: Path | None = None) -> Path:
    """Where the lock file is."""
    home = Path(user_home) if user_home else config_home()
    return home / LOCK_FILE


def _read_json(path: Path) -> dict:
    """A file of ours that holds JSON. It is not JSON: something is wrong with it."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillError(f"{path.name} cannot be read: {error}") from None
    return data if isinstance(data, dict) else {}


def _installed(name: str, item: object) -> Installed | None:
    """One entry of the lock file. An entry that cannot be read is left out."""
    if not isinstance(item, dict):
        return None
    try:
        source = source_of(item.get("source"))
    except SkillError:
        return None
    return Installed(
        name=name,
        source=source,
        sha256=str(item.get("sha256") or ""),
        installed_at=str(item.get("installed_at") or ""),
        files=[
            FileEntry(str(entry.get("path") or ""), int(entry.get("size") or 0), str(entry.get("sha256") or ""))
            for entry in item.get("files") or []
            if isinstance(entry, dict)
        ],
    )


def _name(skill, source: Source, files: list[FileEntry]) -> tuple[str, list[str]]:
    """The name of a staged skill, and what the user should know about it."""
    warnings = []
    name = skill.name
    if not SKILL_NAME.match(name):
        """The name of the skill is a directory name, so it has to be safe."""
        warnings.append(f"the skill calls itself '{skill.name}', which is not a name a skill can have")
        name = sanitize(skill.name)
        if not SKILL_NAME.match(name):
            name = sanitize(_fallback_name(source))
    scripts = [entry.path for entry in files if entry.path.lower().endswith(SCRIPTS)]
    if scripts:
        warnings.append(f"the skill has {len(scripts)} script(s). The model may run them with `bash`.")
    return check_name(name), warnings


def _fallback_name(source: Source) -> str:
    """The name of a skill that does not have a usable one of its own."""
    if source.kind in ("github", "gitee", "git"):
        if source.path:
            return source.path.rstrip("/").split("/")[-1]
        if source.repo:
            return source.repo.split("/")[-1]
        return source.url.rstrip("/").split("/")[-1].removesuffix(".git")
    return source.url.rstrip("/").split("/")[-1].removesuffix(".md")


def _write_stage(staged: Staged, workdir: Path) -> None:
    """Write down what is known about a staged skill."""
    data = {
        "stage_id": staged.stage_id,
        "source": staged.source.as_dict(),
        "name": staged.name,
        "description": staged.description,
        "sha256": staged.sha256,
        "warnings": staged.warnings,
        "files": [{"path": entry.path, "size": entry.size, "sha256": entry.sha256} for entry in staged.files],
    }
    (workdir / STAGE_FILE).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _clear_old_stages(home: Path) -> None:
    """The stages nobody looked at are of no use to anybody."""
    cache = home / CACHE_DIR
    if not cache.is_dir():
        return
    for path in cache.iterdir():
        if path.is_dir() and time.time() - path.stat().st_mtime > STAGE_LIFE:
            shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "CACHE_DIR",
    "Installed",
    "LOCK_FILE",
    "STAGE_LIFE",
    "Staged",
    "check_update",
    "install",
    "lock_path",
    "read_lock",
    "read_stage",
    "stage",
    "uninstall",
    "write_lock",
]
