"""Open a file in the editor of the user.

The editor is the one the user named in `ui.file_opener`: `vscode`, `cursor`,
`windsurf`, or a command of his own. The file is opened in the background: the
agent does not wait for the editor to close.
"""

import shlex
import subprocess
from pathlib import Path

OPENERS = {
    "vscode": "code -g {file}",
    "cursor": "cursor -g {file}",
    "windsurf": "windsurf -g {file}",
}
"""The editors the user may name. The file is where `{file}` says."""


def opener_command(opener: str, path: Path) -> list[str]:
    """The command that opens the file. Empty when there is no opener."""
    if not opener:
        return []
    parts = shlex.split(OPENERS.get(opener, opener))
    if not parts:
        return []
    if "{file}" in parts:
        return [str(path) if part == "{file}" else part for part in parts]
    return [*parts, str(path)]


def open_path(path_text: str, opener: str, cwd: Path) -> str:
    """Open a file and say what happened."""
    if not opener:
        return "No file opener is configured. Set ui.file_opener: vscode, cursor or windsurf."
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = cwd / path
    if not path.exists():
        return f"There is no file '{path}'."
    command = opener_command(opener, path)
    if not command:
        return f"'{opener}' is not a program that opens a file."
    try:
        subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        return f"The file could not be opened: {error}"
    return f"Opened {path} with {command[0]}."
