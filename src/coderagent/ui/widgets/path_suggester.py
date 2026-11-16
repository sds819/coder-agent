"""Complete the path of a file when the user writes `@`."""

import os
import time
from pathlib import Path

from textual.suggester import Suggester

IGNORED = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
"""The directories that hold no file the user wants to mention."""

LISTED_FOR = 5.0
"""The seconds a list of files is used before it is made again."""


class PathSuggester(Suggester):
    """Suggests the path of a file when the user writes `@`.

    The suggestion is the whole input with the path filled in, because that is
    what the widget of textual expects.
    """

    def __init__(self, cwd: Path) -> None:
        super().__init__(case_sensitive=True, use_cache=False)
        """The matching ignores the case, but the path that comes out keeps it."""
        self.cwd = Path(cwd)
        self._paths: list[str] = []
        self._listed = 0.0

    def paths(self) -> list[str]:
        """The files under the working directory, relative to it, the shallow ones first."""
        if self._paths and time.time() - self._listed < LISTED_FOR:
            return self._paths
        found = []
        for root, directories, names in os.walk(self.cwd, followlinks=False):
            directories[:] = [name for name in directories if name not in IGNORED and not name.startswith(".")]
            for name in names:
                found.append(str(Path(root, name).relative_to(self.cwd)))
        self._paths = sorted(found, key=lambda path: (path.count("/"), path))
        self._listed = time.time()
        return self._paths

    async def get_suggestion(self, value: str) -> str | None:
        """The input with the path after the last `@` completed."""
        at = value.rfind("@")
        if at < 0 or (at > 0 and not value[at - 1].isspace()):
            return None
        fragment = value[at + 1 :]
        if " " in fragment:
            return None
        for path in self.paths():
            if path.casefold().startswith(fragment.casefold()):
                return value[: at + 1] + path
        return None
