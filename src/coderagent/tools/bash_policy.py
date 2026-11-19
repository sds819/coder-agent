"""What a shell command is, and where it may reach.

The known commands are a tree of prefixes: `git` has subcommands and they do
not all do the same. A command that only looks around is safe, one that
destroys something or sends it out is dangerous, and the rest is unknown.

The disk is bounded like the file tools are: the working directory is where the
agent works, and the system directories hold the programs it runs.
"""

import os
import re
import shlex
from pathlib import Path

SYSTEM_PREFIXES = ("/bin", "/sbin", "/usr", "/lib", "/lib64", "/opt")
"""Where the programs of the system live. A command may name them."""

VARIABLE = re.compile(r"\$(\w+|\{[A-Za-z_][A-Za-z0-9_]*\})")
"""A variable of a word, like `$HOME` or `${HOME}`."""

COMMANDS: dict[str, object] = {
    # the commands that only look around
    "ls": None,
    "pwd": None,
    "echo": None,
    "cat": None,
    "head": None,
    "tail": None,
    "wc": None,
    "stat": None,
    "file": None,
    "du": None,
    "df": None,
    "tree": None,
    "which": None,
    "basename": None,
    "dirname": None,
    "realpath": None,
    "date": None,
    "whoami": None,
    "id": None,
    "uname": None,
    "hostname": None,
    "diff": None,
    "cmp": None,
    "grep": None,
    "rg": None,
    "jq": None,
    "md5sum": None,
    "shasum": None,
    "git": {
        "status": None,
        "diff": None,
        "log": None,
        "show": None,
        "blame": None,
        "rev-parse": None,
        "ls-files": None,
        "shortlog": None,
        "cat-file": None,
        "describe": None,
        "push": "sends commits to a remote",
        "pull": "changes the working tree from a remote",
        "fetch": "downloads from a remote",
        "clone": "downloads a repository",
        "reset": "throws the commits away",
        "clean": "deletes the files that are not tracked",
        "checkout": "changes the working tree",
        "commit": "writes to the history of the repository",
        "add": "writes to the index of the repository",
        "branch": "changes the branches of the repository",
        "rebase": "rewrites the history of the repository",
        "merge": "merges into the working tree",
        "tag": "changes the tags of the repository",
        "stash": "hides the changes of the working tree",
        "config": "changes the settings of the repository",
        "remote": "changes the remotes of the repository",
        "submodule": "changes the submodules of the repository",
    },
    # the commands that destroy something or send it out
    "rm": "deletes files",
    "rmdir": "deletes directories",
    "mv": "moves files",
    "cp": "copies files",
    "chmod": "changes the permissions of files",
    "chown": "changes the owner of files",
    "dd": "writes blocks to a device",
    "mkfs": "makes a filesystem",
    "curl": "sends data out of the machine",
    "wget": "downloads from the network",
    "ssh": "opens a connection to another machine",
    "scp": "copies files from another machine",
    "sftp": "opens a connection to another machine",
    "rsync": "copies files to another machine",
    "nc": "opens a network connection",
    "kill": "stops a process",
    "killall": "stops the processes of a name",
    "pkill": "stops the processes of a pattern",
    "sudo": "runs a command as another user",
    "su": "runs a shell as another user",
    "docker": "controls the containers",
    "kubectl": "controls the clusters of kubernetes",
    "terraform": "changes the infrastructure",
    "aws": "calls amazon web services",
    "gcloud": "calls google cloud",
    "az": "calls microsoft azure",
    "npm": "installs and runs javascript packages",
    "npx": "runs a javascript package",
    "yarn": "installs and runs javascript packages",
    "pnpm": "installs and runs javascript packages",
    "pip": "installs python packages",
    "pip3": "installs python packages",
    "apt": "installs the packages of the system",
    "apt-get": "installs the packages of the system",
    "yum": "installs the packages of the system",
    "dnf": "installs the packages of the system",
    "brew": "installs the packages of the system",
    "crontab": "changes the jobs of the scheduler",
    "systemctl": "controls the services of the system",
    "launchctl": "controls the services of the system",
}
"""The tree of the known commands. A leaf is `None` when it is safe, a text when it is dangerous."""

_MISSING = object()
"""The marker for a command that is not in the tree."""

NETWORK_COMMANDS = {
    "curl",
    "wget",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "nc",
    "ncat",
    "netcat",
    "telnet",
    "ftp",
    "aria2c",
    "http",
    "https",
    "ping",
    "npm",
    "npx",
    "yarn",
    "pnpm",
    "pip",
    "pip3",
    "uv",
    "poetry",
    "apt",
    "apt-get",
    "yum",
    "dnf",
    "brew",
    "aws",
    "gcloud",
    "az",
    "docker",
    "kubectl",
    "terraform",
    "gh",
    "glab",
}
"""The commands that reach the network."""

NETWORK_SUBCOMMANDS = {"git": ("clone", "fetch", "pull", "push")}
"""The subcommands of a command that reach the network."""

EMBEDDED_PATH = re.compile(r"""['"(]\s*(/[^\s'"()]+)""")
"""An absolute path inside a quoted word, like the file of a small script."""


def segments(command: str) -> list[str]:
    """The parts of a command: what a shell would run one after the other.

    A substitution runs a command too: what is inside `$(...)` or between
    backticks is a part of its own, so it is judged on its own.
    """
    parts: list[str] = []
    current: list[str] = []
    nested: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            current.append(char)
        elif command[index : index + 2] == "$(":
            inner, index = _inside(command, index + 2, ")")
            nested.extend(segments(inner))
        elif char == "`":
            inner, index = _inside(command, index + 1, "`")
            nested.extend(segments(inner))
        elif command[index : index + 2] in ("&&", "||"):
            parts.append("".join(current))
            parts.extend(nested)
            current, nested = [], []
            index += 1
        elif char in ";|\n":
            parts.append("".join(current))
            parts.extend(nested)
            current, nested = [], []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    parts.extend(nested)
    return [part.strip() for part in parts if part.strip()]


def _inside(command: str, start: int, closer: str) -> tuple[str, int]:
    """The text of a substitution, and where it ends."""
    depth = 1
    quote = ""
    index = start
    while index < len(command):
        char = command[index]
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif closer == ")" and char == "(":
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return command[start:index], index + 1
        index += 1
    return command[start:], len(command)


def tokens(segment: str) -> list[str]:
    """The words of a part, with the quotes still on them."""
    lexer = shlex.shlex(segment, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return segment.split()


def classify_segment(segment: str) -> tuple[str, str]:
    """The kind of a part: `safe`, `dangerous` or `unknown`, and why it is dangerous."""
    parts = tokens(segment)
    if not parts:
        return "unknown", ""
    program = parts[0].strip("\"'")
    if "/" in program:
        """A program of a path is not one of the known ones."""
        return "unknown", ""
    if writes(segment):
        """A command that redirects writes something, whatever it is."""
        return "unknown", ""
    value = COMMANDS.get(program, _MISSING)
    if isinstance(value, dict):
        subcommand = _subcommand(parts[1:])
        value = value.get(subcommand, _MISSING) if subcommand else _MISSING
    if value is _MISSING:
        return "unknown", ""
    if value is None:
        return "safe", ""
    return "dangerous", str(value)


def classify(command: str) -> tuple[str, str]:
    """The kind of a command: the strictest of its parts."""
    kinds = [classify_segment(segment) for segment in segments(command)]
    if not kinds:
        return "unknown", ""
    if any(kind == "dangerous" for kind, _ in kinds):
        return "dangerous", next(reason for kind, reason in kinds if kind == "dangerous")
    if all(kind == "safe" for kind, _ in kinds):
        return "safe", ""
    return "unknown", ""


def needs_network(segment: str) -> str:
    """Why a part of a command reaches the network, empty when it does not.

    Only the known commands are looked at: a program that is not known may
    reach the network, but the policy cannot tell.
    """
    parts = tokens(segment)
    if not parts:
        return ""
    program = parts[0].strip("\"'")
    if "/" in program:
        """A program of a path is not one of the known ones."""
        return ""
    if program in NETWORK_COMMANDS:
        return f"'{program}' reaches the network"
    subcommands = NETWORK_SUBCOMMANDS.get(program)
    if subcommands:
        """Every word is looked at: `git -C /tmp push` is a push."""
        for argument in parts[1:]:
            value = argument.strip("\"'")
            if value in subcommands:
                return f"'{program} {value}' reaches the network"
    return ""


def writes(segment: str) -> bool:
    """Whether a part writes a file with a redirection."""
    parts = tokens(segment)
    for index, token in enumerate(parts):
        value = token.strip("\"'")
        if value in (">", ">>"):
            target = parts[index + 1].strip("\"'") if index + 1 < len(parts) else ""
        elif ">" in value:
            target = value.split(">", 1)[1]
        else:
            continue
        if target and not target.startswith("/dev/null"):
            return True
    return False


def outside_paths(command: str, cwd: Path, include_dirs: list[Path]) -> list[str]:
    """The paths a command reaches that are outside the working directory.

    The system directories are open for the programs, the working directory for
    everything else. A command that changes the directory moves the ground the
    paths after it are relative to. The variables of the command are expanded
    first: a path that hides behind `$HOME` is a path all the same.
    """
    outside: list[str] = []
    cwd = Path(cwd).resolve()
    include_dirs = [_resolve(directory, cwd) for directory in include_dirs]
    virtual = cwd
    variables: dict[str, str] = {}
    for segment in segments(command):
        parts = tokens(segment)
        if not parts:
            continue
        program = parts[0].strip("\"'")
        _remember(variables, program)
        program = _expand(program, variables)
        if "/" in program and not _allowed(_resolve(program, virtual), cwd, include_dirs, system=True):
            outside.append(program)
        for token in parts[1:]:
            _remember(variables, token)
            for candidate in _candidates(token.strip("\"'"), variables):
                if not _allowed(_resolve(candidate, virtual), cwd, include_dirs):
                    outside.append(candidate)
        if Path(program).name == "cd" and len(parts) > 1:
            target = parts[1].strip("\"'")
            resolved = _resolve(target, virtual)
            if not _allowed(resolved, cwd, include_dirs):
                outside.append(target)
            else:
                virtual = resolved
    return outside


def named_paths(command: str, cwd: Path) -> list[str]:
    """The paths a command names, relative to the working directory.

    A word is taken for a path when it looks like one — it has a separator or
    a dot in it — or when there is something of that name on the disk. The
    variables are expanded first, and a command that changes the directory
    moves the ground the paths after it are relative to.
    """
    cwd = Path(cwd).resolve()
    virtual = cwd
    variables: dict[str, str] = {}
    found: list[str] = []
    for segment in segments(command):
        parts = tokens(segment)
        for token in parts:
            value = token.strip("\"'")
            _remember(variables, value)
            for candidate in _path_words(_assigned(value), variables):
                resolved = _resolve(candidate, virtual)
                if not ("/" in candidate or "." in candidate or resolved.exists()):
                    continue
                found.append(
                    resolved.relative_to(cwd).as_posix() if resolved.is_relative_to(cwd) else resolved.as_posix()
                )
        if parts and Path(parts[0].strip("\"'")).name == "cd" and len(parts) > 1:
            virtual = _resolve(parts[1].strip("\"'"), virtual)
    return found


def _assigned(value: str) -> str:
    """The path of an assignment: what follows the equal sign."""
    name, separator, assignment = value.partition("=")
    if separator and (name.isidentifier() or name.startswith("-")):
        return assignment.strip("\"'")
    return value


def _path_words(value: str, variables: dict[str, str]) -> list[str]:
    """The words of a value that may name a path."""
    value = _expand(value, variables)
    if not value or value.startswith("-"):
        return []
    words = []
    for part in [value, *EMBEDDED_PATH.findall(value)]:
        part = part.strip("\"'")
        if part and not part.startswith("-"):
            words.append(part)
    return words


def _subcommand(arguments: list[str]) -> str:
    """The first argument that is not a flag."""
    for argument in arguments:
        value = argument.strip("\"'")
        if not value.startswith("-"):
            return value
    return ""


def _candidates(value: str, variables: dict[str, str]) -> list[str]:
    """The paths a word names: the absolute ones, the home ones and the ones that climb out."""
    if not value:
        return []
    value = _expand(value, variables)
    if value.startswith("$") or ":" in value:
        """A list of paths, like `$PATH`, is not one path."""
        return []
    candidates: list[str] = []
    for part in [value, *EMBEDDED_PATH.findall(value)]:
        part = part.strip("\"'")
        if not part:
            continue
        for half in [part, *part.split("=")[1:]]:
            half = half.strip("\"'")
            if half.startswith("/") or half.startswith("~"):
                candidates.append(half)
            elif ".." in half.split("/"):
                candidates.append(half)
    return candidates


def _expand(value: str, variables: dict[str, str]) -> str:
    """The variables of a word, as the shell would see them.

    A variable that is not set is empty, like it is for the shell: the rest of
    the word may still name a path.
    """

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name.startswith("{"):
            name = name[1:-1]
        return variables.get(name, os.environ.get(name, ""))

    return VARIABLE.sub(replace, value)


def _remember(variables: dict[str, str], token: str) -> None:
    """The value of an assignment, so that the words after it see it."""
    name, separator, value = token.partition("=")
    if separator and value and name.isidentifier():
        variables[name] = value.strip("\"'")


def _resolve(path: str | Path, base: Path) -> Path:
    """Where a path is, relative to the directory the command is in."""
    text = str(path)
    if text.startswith("~"):
        return Path(text).expanduser().resolve()
    if text.startswith("/"):
        return Path(text).resolve()
    return (base / text).resolve()


def _allowed(path: Path, cwd: Path, include_dirs: list[Path], system: bool = False) -> bool:
    """Whether a path is one the agent may touch."""
    if path.is_relative_to(cwd):
        return True
    if any(path.is_relative_to(directory) for directory in include_dirs):
        return True
    if system:
        return any(str(path).startswith(prefix) for prefix in SYSTEM_PREFIXES)
    return False
