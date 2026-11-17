"""Instruction files: the AGENTS.md / CLAUDE.md files that tell the agent how to work here.

The user level comes first, then the project level. Files in subdirectories are
loaded lazily, when a tool touches something inside them.
"""

from dataclasses import dataclass
from pathlib import Path

from coderagent.paths import config_home

USER_FILE = "CLAUDE.md"


@dataclass
class InstructionBlock:
    source: str
    content: str
    path: Path

    def render(self) -> str:
        return f'<project_instructions source="{self.source}">\n{self.content.strip()}\n</project_instructions>'


def read_block(path: Path, max_bytes: int = 0) -> InstructionBlock | None:
    """The instructions of a file. A file that is too long is cut short."""
    if not path.exists():
        return None
    raw = path.read_bytes()
    if max_bytes and len(raw) > max_bytes:
        raw = raw[:max_bytes]
        content = raw.decode("utf-8", errors="replace").strip()
        content = f"{content}\n\n[the file is longer than {max_bytes} bytes, the rest of it is not shown]"
    else:
        content = raw.decode("utf-8", errors="replace").strip()
    if not content:
        return None
    return InstructionBlock(source=path.name, content=content, path=path)


def once_per_file(blocks: list[InstructionBlock]) -> list[InstructionBlock]:
    """The blocks, one per file. The last one of a file wins.

    A file can be an instruction and a memory at the same time, and then it is
    read twice but shown once.
    """
    by_path: dict[Path, InstructionBlock] = {}
    for block in blocks:
        by_path[block.path] = block
    return list(by_path.values())


def project_root(cwd: Path) -> Path:
    """The root of the repository the directory belongs to.

    A directory that is not in a repository is its own root.
    """
    directory = Path(cwd).resolve()
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            """A worktree has a file there, a clone has a directory. Both count."""
            return candidate
    return directory


def load_instructions(cwd: Path, user_home: Path | None = None, max_bytes: int = 0) -> list[InstructionBlock]:
    """The user level and the project level instructions, in that order.

    The rules of the repository come before the rules of the directory, so that
    the ones of the directory win when they are read.
    """
    blocks = []
    home = Path(user_home) if user_home else config_home()
    root = project_root(cwd)
    paths = [home / USER_FILE]
    if root != Path(cwd).resolve():
        paths += [root / "AGENTS.md", root / "CLAUDE.md"]
    paths += [Path(cwd) / "AGENTS.md", Path(cwd) / "CLAUDE.md"]
    for path in paths:
        block = read_block(path, max_bytes)
        if block:
            blocks.append(block)
    return blocks


def subdirectory_instructions(path: Path, cwd: Path, max_bytes: int = 0) -> list[InstructionBlock]:
    """The instruction files of the directories between `cwd` and `path`, deepest first."""
    try:
        relative = Path(path).resolve().relative_to(Path(cwd).resolve())
    except ValueError:
        return []
    blocks = []
    directories = list(relative.parts[:-1]) if relative.name else list(relative.parts)
    for index in range(len(directories), 0, -1):
        directory = Path(cwd).joinpath(*directories[:index])
        block = read_block(directory / "AGENTS.md", max_bytes)
        if block:
            blocks.append(block)
    return blocks
