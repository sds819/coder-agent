"""The boundaries of a downloaded skill: how big, how deep, and where.

A skill comes from the network, so nothing in it may be taken for granted: a
path may leave the directory it should stay in, a file may be enormous, and a
link may point anywhere. Everything is checked here, before a byte lands in
the directory of the user.
"""

import hashlib
import os
import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from coderagent.skills.errors import SkillError

SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
"""The names a skill may have. The name is a directory name, so it has to be safe."""

RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
"""The names Windows does not allow. A skill that has one is no use there."""

CHUNK = 64 * 1024
"""How many bytes are read at a time when a file is written."""


@dataclass(frozen=True)
class Policy:
    """What a download may do and how big a skill may be."""

    max_bytes: int = 8 * 1024 * 1024
    """How many bytes a download may take."""
    max_file_bytes: int = 1024 * 1024
    """How many bytes one file of a skill may have."""
    max_files: int = 2000
    """How many files a skill may have."""
    max_depth: int = 16
    """How deep the directories of a skill may go."""
    timeout: int = 30
    """The seconds a download may take."""
    allow_insecure: bool = False
    """Whether `http://` may be fetched. `https://` is the rule."""
    allowed_hosts: tuple[str, ...] = ()
    """The hosts that may point inside the network."""

    @classmethod
    def from_config(cls, config) -> "Policy":
        """The policy of a section of the configuration."""
        return cls(
            max_bytes=config.max_bytes,
            max_file_bytes=config.max_file_bytes,
            max_files=config.max_files,
            max_depth=config.max_depth,
            timeout=config.timeout,
            allow_insecure=config.allow_insecure,
            allowed_hosts=tuple(config.allowed_hosts),
        )


@dataclass(frozen=True)
class FileEntry:
    """One file of a skill."""

    path: str
    """The path of the file, relative to the directory of the skill."""
    size: int
    sha256: str


def digest(files: list[FileEntry]) -> str:
    """One digest of a whole skill, the same whatever the order of the files."""
    joined = "\n".join(f"{entry.path}:{entry.sha256}" for entry in sorted(files, key=lambda entry: entry.path))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def sha256_of(path: Path) -> str:
    """The digest of a file."""
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            sha.update(chunk)
    return sha.hexdigest()


def check_name(name: str) -> str:
    """The name of a skill, when it is one a skill may have."""
    if not SKILL_NAME.match(name):
        raise SkillError(f"'{name}' is not a name a skill can have")
    return name


def sanitize(text: str) -> str:
    """A name a skill may have, made out of anything.

    The name of a skill is a directory name: it is turned into lower case and
    the characters that do not belong are replaced.
    """
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-.")
    return cleaned[:64]


def check_path(root: Path, relative: str) -> Path:
    """The path of a file inside the root, or an error when it would leave.

    The check is on the resolved path, not on the text: `a/../../b` and a
    directory that is a link to somewhere else both leave the root.
    """
    parts = PurePosixPath(relative).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise SkillError(f"'{relative}' is not a path inside the skill")
    for part in parts:
        if ":" in part:
            raise SkillError(f"'{relative}' has a name that is not allowed")
        if part.split(".")[0].upper() in RESERVED:
            raise SkillError(f"'{relative}' has a name that Windows does not allow")
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise SkillError(f"'{relative}' points outside the skill")
    return target


def unpack_tar(archive: Path, dest: Path, policy: Policy, prefix: str = "") -> list[FileEntry]:
    """Unpack a tarball into a directory, refusing what does not belong there.

    The members are checked one by one: only plain files and directories are
    taken, the paths may not leave the directory, and the sizes may not pass
    the policy. The first directory of the archive is dropped: it is the name
    GitHub gives it, not a part of the skill.

    With `prefix` only the part of the archive under that directory is taken:
    a repository may be big, but a skill is small.
    """
    entries: list[FileEntry] = []
    total = 0
    dest.mkdir(parents=True, exist_ok=True)
    prefix = prefix.strip("/")
    try:
        with tarfile.open(archive, "r:*") as tar:
            members = tar.getmembers()
            root = _root_of(members)
            for member in members:
                if member.name.startswith("/"):
                    raise SkillError(f"'{member.name}' is not a path inside the skill")
                relative = _relative(member.name, root)
                if prefix:
                    if relative == prefix:
                        continue
                    if not relative.startswith(f"{prefix}/"):
                        continue
                    relative = relative[len(prefix) + 1 :]
                if not relative:
                    continue
                if not (member.isfile() or member.isdir()):
                    raise SkillError(f"'{member.name}' is not a plain file")
                if len(PurePosixPath(relative).parts) > policy.max_depth:
                    raise SkillError(f"'{relative}' is deeper than {policy.max_depth} levels")
                target = check_path(dest, relative)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if len(entries) >= policy.max_files:
                    raise SkillError(f"the skill has more than {policy.max_files} files")
                if member.size > policy.max_file_bytes:
                    raise SkillError(f"'{relative}' is bigger than {policy.max_file_bytes} bytes")
                total += member.size
                if total > policy.max_bytes:
                    raise SkillError(f"the skill is bigger than {policy.max_bytes} bytes")
                handle = tar.extractfile(member)
                if handle is None:
                    raise SkillError(f"'{relative}' cannot be read")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as output:
                    shutil.copyfileobj(handle, output, CHUNK)
                entries.append(FileEntry(relative, member.size, sha256_of(target)))
    except tarfile.TarError as error:
        raise SkillError(f"the archive cannot be read: {error}") from None
    return entries


def copy_tree(source: Path, dest: Path, policy: Policy) -> list[FileEntry]:
    """Copy a directory of a repository into the directory of a skill.

    A repository is not an archive: it may hold links, and it may hold
    anything. The same checks as for an archive are made here.
    """
    entries: list[FileEntry] = []
    total = 0
    for directory, dirnames, filenames in os.walk(source, followlinks=False):
        base = Path(directory)
        for name in dirnames:
            if (base / name).is_symlink():
                raise SkillError(f"'{name}' is a link, it is not allowed")
        for name in filenames:
            path = base / name
            relative = path.relative_to(source).as_posix()
            if path.is_symlink():
                raise SkillError(f"'{relative}' is a link, it is not allowed")
            if not path.is_file():
                raise SkillError(f"'{relative}' is not a plain file")
            if len(PurePosixPath(relative).parts) > policy.max_depth:
                raise SkillError(f"'{relative}' is deeper than {policy.max_depth} levels")
            if len(entries) >= policy.max_files:
                raise SkillError(f"the skill has more than {policy.max_files} files")
            size = path.stat().st_size
            if size > policy.max_file_bytes:
                raise SkillError(f"'{relative}' is bigger than {policy.max_file_bytes} bytes")
            total += size
            if total > policy.max_bytes:
                raise SkillError(f"the skill is bigger than {policy.max_bytes} bytes")
            target = check_path(dest, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            entries.append(FileEntry(relative, size, sha256_of(target)))
    return entries


def entries_of(directory: Path) -> list[FileEntry]:
    """The files of a directory, with their size and their digest."""
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        entries.append(FileEntry(path.relative_to(directory).as_posix(), path.stat().st_size, sha256_of(path)))
    return entries


def _root_of(members: list[tarfile.TarInfo]) -> str:
    """The directory every member of the archive is under, when there is one.

    The archive of GitHub holds the directory of the repository as a member of
    its own: that member names the root, but it is not a part of the skill.
    A plain file at the top says there is no root at all.
    """
    roots = set()
    for member in members:
        parts = PurePosixPath(member.name).parts
        if not parts:
            return ""
        if len(parts) == 1 and not member.isdir():
            return ""
        roots.add(parts[0])
    return roots.pop() if len(roots) == 1 else ""


def _relative(name: str, root: str) -> str:
    """The path of a member, without the directory the archive is under."""
    parts = list(PurePosixPath(name).parts)
    if root and parts and parts[0] == root:
        parts = parts[1:]
    return "/".join(parts)


__all__ = [
    "CHUNK",
    "FileEntry",
    "Policy",
    "RESERVED",
    "SKILL_NAME",
    "check_name",
    "check_path",
    "copy_tree",
    "digest",
    "entries_of",
    "sanitize",
    "sha256_of",
    "unpack_tar",
]
