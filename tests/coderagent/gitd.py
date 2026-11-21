"""A git server on the machine itself, so that the tests need no network."""

import socket
import subprocess
import time
from pathlib import Path


def free_port() -> int:
    """A port that nothing listens on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class GitDaemon:
    """A repository of skills that is served over the git protocol."""

    def __init__(self, base: Path):
        self.base = base
        self.bare = base / "remote.git"
        subprocess.run(
            ["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare)],
            check=True,
        )
        self.port = free_port()
        self.process = subprocess.Popen(
            [
                "git",
                "daemon",
                "--export-all",
                f"--base-path={base}",
                f"--port={self.port}",
                "--reuseaddr",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait()

    def _wait(self, timeout: float = 10.0) -> None:
        """Wait until the daemon listens."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("the git daemon did not start")

    @property
    def url(self) -> str:
        """The address of the repository."""
        return f"git://127.0.0.1:{self.port}/remote.git"

    def push(self, skills: dict[str, str]) -> None:
        """Put the skills into the repository that is served."""
        work = self.base / "work"
        if not (work / ".git").is_dir():
            subprocess.run(["git", "init", "--quiet", "--initial-branch=main", str(work)], check=True)
        for name, description in skills.items():
            directory = work / "skills" / name
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {description}\n---\n\nThe body of {name}.\n",
                encoding="utf-8",
            )
        subprocess.run(["git", "-C", str(work), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(work),
                "-c",
                "user.email=tests@example.com",
                "-c",
                "user.name=tests",
                "commit",
                "--quiet",
                "-m",
                "the skills",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(work), "push", "--quiet", f"file://{self.bare}", "main"], check=True)

    def close(self) -> None:
        """Stop the daemon."""
        self.process.terminate()
        self.process.wait(timeout=10)
