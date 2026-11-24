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
    """The files of the directories that are open to the agent, with the ones that changed marked."""

    def __init__(self, cwd: Path, roots: list[Path] | None = None, **kwargs) -> None:
        self.cwd = Path(cwd)
        self.roots = [Path(root) for root in (roots or [self.cwd])]
        """The directories the user opened to the agent: the tree lists those and nothing else."""
        super().__init__(self.roots[0].name if len(self.roots) == 1 else "files", **kwargs)
        self.show_root = False
        self.display = False
        """The tree is hidden until the user asks for it."""

    def reload(self) -> None:
        """Read the directories again and show what is there now."""
        self.clear()
        for root in self.roots:
            parent = self.root if len(self.roots) == 1 else self.root.add(root.name + "/", data=root.as_posix())
            self._fill(parent, root)

    def _fill(self, parent, root: Path) -> None:
        """The entries of a directory, under the node that holds it."""
        changes = changed_files(root)
        nodes = {Path("."): parent}
        for path, kind in list_entries(root, MAX_DEPTH):
            relative = path.relative_to(root)
            node_parent = nodes.get(relative.parent)
            if node_parent is None:
                continue
            label = f"{relative.name}/" if kind == "d" else relative.name
            mark = mark_of(changes.get(relative.as_posix(), ""))
            if mark:
                label = f"{mark} {label}"
            node = (
                node_parent.add_leaf(label, data=self._data(path))
                if kind == "f"
                else node_parent.add(label, data=self._data(path))
            )
            nodes[relative] = node

    def _data(self, path: Path) -> str:
        """The path of a node, the way the agent can be given it.

        A file of the working directory is named relative to it; a file of another
        directory has to be named with its whole path.
        """
        try:
            return path.relative_to(self.cwd).as_posix()
        except ValueError:
            return path.as_posix()
