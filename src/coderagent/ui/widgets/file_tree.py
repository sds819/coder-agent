"""The tree of the working directory, beside the conversation."""

import subprocess
from pathlib import Path

from textual.widgets import Tree

from coderagent.tools.builtin.search import list_entries

MAX_DEPTH = 3
"""How many levels of directories the tree shows."""

MARKS = {"M": "●", "A": "+", "?": "?", "D": "-", "R": "●"}
"""The mark of a file that git knows about: changed, added, untracked, deleted."""


def mark_of(status: str) -> str:
    """The mark of a file with this git status."""
    if "?" in status:
        return MARKS["?"]
    if "D" in status:
        return MARKS["D"]
    if "A" in status:
        return MARKS["A"]
    if "M" in status or "R" in status:
        return MARKS["M"]
    return ""


def changed_files(cwd: Path) -> dict[str, str]:
    """The files that git says are changed. Empty when there is no git here."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    changes = {}
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            """A file that was renamed: the new name is the one that matters."""
            path = path.split(" -> ")[-1]
        changes[path] = line[:2].strip() or "?"
    return changes


class FileTree(Tree):
    """The files of the working directory, with the ones that changed marked."""

    def __init__(self, cwd: Path, **kwargs) -> None:
        super().__init__(Path(cwd).name, **kwargs)
        self.cwd = Path(cwd)
        self.show_root = False
        self.display = False
        """The tree is hidden until the user asks for it."""

    def reload(self) -> None:
        """Read the directory again and show what is there now."""
        self.clear()
        changes = changed_files(self.cwd)
        nodes = {Path("."): self.root}
        for path, kind in list_entries(self.cwd, MAX_DEPTH):
            relative = path.relative_to(self.cwd)
            parent = nodes.get(relative.parent)
            if parent is None:
                continue
            label = f"{relative.name}/" if kind == "d" else relative.name
            mark = mark_of(changes.get(relative.as_posix(), ""))
            if mark:
                label = f"{mark} {label}"
            node = (
                parent.add_leaf(label, data=relative.as_posix())
                if kind == "f"
                else parent.add(label, data=relative.as_posix())
            )
            nodes[relative] = node
