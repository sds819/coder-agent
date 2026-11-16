"""The boundary of the commands, enforced by the operating system.

The permission layer asks the user. This one asks nobody: the commands of the
agent run inside a Seatbelt profile (macOS) or inside a bubblewrap namespace
(Linux), so a command that goes too far is stopped by the kernel and not by a
rule in a file.

The modes are the ones of Codex:

| Mode | What the commands may do |
|---|---|
| `full-access` | Everything the user may do. The default. |
| `workspace-write` | Read the disk, write inside the working directory |
| `read-only` | Read the disk, write nothing |

The commands are wrapped, not the tools: the file tools of the agent write
through the operating system of the user, and the permission layer is what
keeps them inside the bounds.
"""

import platform
import shlex
import shutil
import tempfile
from pathlib import Path

READ_ONLY = "read-only"
WORKSPACE_WRITE = "workspace-write"
FULL_ACCESS = "full-access"
MODES = (READ_ONLY, WORKSPACE_WRITE, FULL_ACCESS)
"""The modes from the tightest to the loosest."""


class UnsupportedSandbox(RuntimeError):
    """The mode cannot be enforced on this machine."""


def scratch_dir() -> Path:
    """The directory the commands may always write to, even in the read-only mode.

    A build needs somewhere to put its files, and a temporary file is not a
    change of the machine.
    """
    return Path(tempfile.gettempdir()).resolve()


class Confinement:
    """The OS level boundary around the commands of a session."""

    def __init__(
        self,
        mode: str,
        cwd: Path,
        include_dirs: list[str] | None = None,
        network: str = "allow",
        scratch: Path | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown sandbox mode '{mode}'. Use one of: {', '.join(MODES)}.")
        self.mode = mode
        self.cwd = Path(cwd).resolve()
        self.include_dirs = [Path(directory).resolve() for directory in include_dirs or []]
        self.network = network
        """Whether the commands may reach the network. `deny` closes it in the sandbox too."""
        self.scratch = Path(scratch).resolve() if scratch else scratch_dir()
        """The one directory the commands may write to, even in the read-only mode."""
        self.tool = self._tool() if mode != FULL_ACCESS else ""

    @property
    def active(self) -> bool:
        """Whether the commands run inside a sandbox at all."""
        return self.mode != FULL_ACCESS

    def writable(self) -> list[Path]:
        """The directories the commands may write to."""
        if not self.active:
            return []
        if self.mode == READ_ONLY:
            return [self.scratch]
        return [self.scratch, self.cwd, *self.include_dirs]

    def wrap(self, command: str) -> str:
        """The command, with the sandbox in front of it.

        The command goes to the sandbox as one argument, so the shell that
        parses it runs inside the sandbox too. A pipeline that was parsed
        outside would run half of it outside.
        """
        if not self.active:
            return command
        return f"{self._prefix()} /bin/sh -c {shlex.quote(command)}"

    def _tool(self) -> str:
        """The program that builds the sandbox."""
        return find_tool(platform.system(), self.mode)

    def _prefix(self) -> str:
        if platform.system() == "Darwin":
            return " ".join(shlex.quote(part) for part in [self.tool, "-p", self._profile()])
        return " ".join(shlex.quote(part) for part in self._bubblewrap())

    def _profile(self) -> str:
        """The Seatbelt profile. The last rule that matches is the one that holds."""
        lines = ["(version 1)", "(allow default)", "(deny file-write*)"]
        lines += [f'(allow file-write* (subpath "{_escape(path)}"))' for path in self.writable()]
        if self.network == "deny":
            lines.append("(deny network*)")
        return "\n".join(lines)

    def _bubblewrap(self) -> list[str]:
        """The arguments of bubblewrap. The disk is read only, except for the writable directories."""
        args = [self.tool, "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev"]
        for path in self.writable():
            args += ["--bind", str(path), str(path)]
        if self.network == "deny":
            args.append("--unshare-net")
        return args


def _escape(path: Path) -> str:
    """A path as the Seatbelt profile wants it."""
    return path.as_posix().replace('"', '\\"')


SANDBOX_TOOLS = {"Darwin": ("sandbox-exec", "Seatbelt"), "Linux": ("bwrap", "bubblewrap")}
"""The program that builds the sandbox on a system, and the name of the technology."""


def find_tool(system: str, mode: str) -> str:
    """The program that builds the sandbox on this system."""
    if system not in SANDBOX_TOOLS:
        raise UnsupportedSandbox(f"The {mode} mode is not supported on {system}.")
    program, name = SANDBOX_TOOLS[system]
    tool = shutil.which(program)
    if not tool:
        raise UnsupportedSandbox(f"The {mode} mode needs {name} (`{program}`), which this machine does not have.")
    return tool


SANDBOX_NOTES = {
    READ_ONLY: (
        "The commands run in a read-only sandbox: they may read the disk, but they may not write "
        "anything outside the scratch directory. The tools that write files are refused as well. "
        "Answer with what you found and describe the change you would make, but do not make it."
    ),
    WORKSPACE_WRITE: (
        "The commands run in a sandbox: they may read the disk, but they may only write inside the working directory."
    ),
}
"""What the model is told when the sandbox takes something away from it."""


def sandbox_block(mode: str) -> str:
    """The note as the block the model sees, empty when the commands may do everything."""
    note = SANDBOX_NOTES.get(mode, "")
    if not note:
        return ""
    return f'<sandbox mode="{mode}">\n{note}\n</sandbox>'


def build(
    mode: str,
    cwd: Path,
    include_dirs: list[str] | None = None,
    network: str = "allow",
    scratch: Path | None = None,
) -> Confinement | None:
    """The confinement of a sandbox, or nothing when the commands may do everything."""
    if mode == FULL_ACCESS:
        return None
    return Confinement(mode, cwd, include_dirs, network, scratch)


__all__ = [
    "FULL_ACCESS",
    "MODES",
    "READ_ONLY",
    "WORKSPACE_WRITE",
    "Confinement",
    "UnsupportedSandbox",
    "build",
    "find_tool",
    "sandbox_block",
]
