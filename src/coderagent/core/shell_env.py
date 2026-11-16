"""The environment that the commands of the agent see.

The commands of the agent run on the machine of the user, and the environment
of the user holds the keys of the providers. The agent does not need them: the
model calls the provider from the process of the agent, not from the shell. A
key that the shell can print is a key that the model reads, and then the key
is in the transcript of the session.

So the keys stay out of the shell. The user may open them again with the
`include` list, when a script of the project needs one.
"""

from fnmatch import fnmatchcase

CORE = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "TEMP",
    "TMP",
    "USER",
    "LOGNAME",
    "SHELL",
    "TZ",
    "PWD",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)
"""The variables that a command needs to work at all."""

SECRETS = (
    "*_API_KEY",
    "*_KEY",
    "*_TOKEN",
    "*_SECRET",
    "*_PASSWORD",
    "*_PASSWD",
    "*_CREDENTIALS",
    "*_ACCESS_KEY",
)
"""The patterns of the names that never reach the shell of the agent."""

INHERITS = ("all", "core", "none")
"""How much of the environment of the user the agent sees."""


def build(inherit: str, exclude: list[str], include: list[str], overrides: dict, environ: dict) -> dict[str, str]:
    """The environment the commands of the agent see."""
    if inherit == "none":
        env: dict[str, str] = {}
    elif inherit == "core":
        env = {name: value for name, value in environ.items() if name in CORE}
    else:
        env = dict(environ)
    for name in [name for name in env if _hidden(name, exclude, include)]:
        env.pop(name)
    env.update(overrides)
    return env


def _hidden(name: str, exclude: list[str], include: list[str]) -> bool:
    """Whether a variable stays out of the shell of the agent."""
    if any(fnmatchcase(name, pattern) for pattern in include):
        """The user opened it again on purpose."""
        return False
    return any(fnmatchcase(name, pattern) for pattern in (*SECRETS, *exclude))


__all__ = ["CORE", "INHERITS", "SECRETS", "build"]
