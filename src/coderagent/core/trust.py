"""What the user has agreed to run.

An MCP server, a hook and a verify command run code without asking the user:
one call after the other, without a question. When they come from the project,
that code was not written by the user, and cloning a repository must not be
enough to run it. So the code of a project waits for a decision, and the
decision is remembered in `~/.coderagent/trusted.json`.

The decision belongs to the command it was made for: a thing that changed its
command is a thing that has to be trusted again.
"""

import copy
import hashlib
import json
from pathlib import Path

from coderagent.paths import config_home

TRUST_FILE = "trusted.json"
TRUSTED = "trusted"
DENIED = "denied"
TIGHT_MODES = ("plan", "readonly")
"""The modes a project may set: they take tools away, they never give them."""
TIGHT_SANDBOX_MODES = ("read-only", "workspace-write")
"""The sandbox modes a project may set: they close the sandbox, they never open it."""


def trust_path(user_home: Path | None = None) -> Path:
    """The file with the decisions of the user."""
    home = Path(user_home) if user_home else config_home()
    return home / TRUST_FILE


def decisions(user_home: Path | None = None) -> dict[str, dict[str, dict]]:
    """Every decision of the user, per project."""
    path = trust_path(user_home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def project_key(project: Path) -> str:
    """The key of a project: the directory whose configuration it is."""
    return str(Path(project).resolve())


def decision(project: Path, key: str, command: str, user_home: Path | None = None) -> str:
    """The decision for a thing of a project. Empty when there is none.

    The command has to be the one that was trusted: when it changes, the thing
    has to be trusted again.
    """
    record = decisions(user_home).get(project_key(project), {}).get(key)
    if not isinstance(record, dict) or record.get("command") != command:
        return ""
    return str(record.get("decision", ""))


def is_trusted(project: Path, key: str, command: str, user_home: Path | None = None) -> bool:
    """Whether the user has trusted this command of this project."""
    return decision(project, key, command, user_home) == TRUSTED


def remember(project: Path, key: str, answer: str, command: str, user_home: Path | None = None) -> Path:
    """Write the answer of the user into the trust table."""
    path = trust_path(user_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = decisions(user_home)
    table.setdefault(project_key(project), {})[key] = {"decision": answer, "command": command}
    path.write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    return path


def key_of(kind: str, command: str) -> str:
    """A short key for a thing that has no name of its own."""
    return f"{kind}:{hashlib.sha256(command.encode('utf-8')).hexdigest()[:8]}"


def waiting(project: dict, directory: Path, user_home: Path | None = None) -> dict[str, str]:
    """The code of the project that waits for a decision of the user.

    The key names the thing, the value is the command it would run.
    """
    pending: dict[str, str] = {}
    for server in _entries(project, "mcp", "servers"):
        command = str(server.get("command") or "")
        key = f"mcp:{server.get('name')}"
        if command and not is_trusted(directory, key, command, user_home):
            pending[key] = command
    for hook in _hooks(project):
        command = str(hook.get("command") or "")
        key = key_of("hook", command)
        if command and not is_trusted(directory, key, command, user_home):
            pending[key] = command
    for command in _entries(project, "verify", "commands"):
        command = str(command)
        key = key_of("verify", command)
        if command and not is_trusted(directory, key, command, user_home):
            pending[key] = command
    return pending


def without_untrusted(project: dict, directory: Path, user_home: Path | None = None) -> dict:
    """The configuration of the project without the code that waits for a decision.

    What is left out is left out entirely, so that the user level keeps what
    it has: a project that is not trusted does not replace the user, it only
    misses.
    """
    pending = waiting(project, directory, user_home)
    if not pending:
        return project
    result = copy.deepcopy(project)
    result.pop("profile", None)
    result.pop("profiles", None)
    """A project may not choose a set of permissions: that is the decision of the user."""
    _without_servers(result, pending)
    _without_hooks(result, pending)
    _without_verify(result, pending)
    return result


def _without_servers(result: dict, pending: dict[str, str]) -> None:
    """The servers that are left are the ones the user has trusted."""
    servers = _entries(result, "mcp", "servers")
    kept = [server for server in servers if f"mcp:{server.get('name')}" not in pending]
    if len(kept) == len(servers):
        return
    if kept:
        result["mcp"]["servers"] = kept
    else:
        result["mcp"].pop("servers", None)


def _without_hooks(result: dict, pending: dict[str, str]) -> None:
    """The hooks that are left are the ones the user has trusted."""
    events = (result.get("hooks") or {}).get("events") or {}
    for event, group in list(events.items()):
        matchers = []
        for matcher in group or []:
            hooks = [
                h for h in (matcher.get("hooks") or []) if key_of("hook", str(h.get("command") or "")) not in pending
            ]
            if hooks:
                matcher["hooks"] = hooks
                matchers.append(matcher)
        if matchers:
            events[event] = matchers
        else:
            events.pop(event, None)


def _without_verify(result: dict, pending: dict[str, str]) -> None:
    """The commands that are left are the ones the user has trusted."""
    commands = _entries(result, "verify", "commands")
    kept = [command for command in commands if key_of("verify", str(command)) not in pending]
    if len(kept) == len(commands):
        return
    if kept:
        result["verify"]["commands"] = kept
    else:
        result["verify"].pop("commands", None)


def tightened(project: dict) -> dict:
    """The configuration of the project without what would loosen the permissions.

    The permissions are the user's: a project may say what the agent may not
    do, never what it may do without asking. So the mode of the project is only
    kept when it takes tools away, the directories it opens are dropped, and
    the rules it brings may only deny.
    """
    result = copy.deepcopy(project)
    result.pop("profile", None)
    result.pop("profiles", None)
    """A project may not choose a set of permissions: that is the decision of the user."""
    sandbox = result.get("sandbox")
    if isinstance(sandbox, dict) and str(sandbox.get("mode") or "") not in TIGHT_SANDBOX_MODES:
        """A project may close the sandbox, never open it."""
        sandbox.pop("mode", None)
    telemetry = result.get("telemetry")
    if isinstance(telemetry, dict):
        if str(telemetry.get("otel_endpoint") or ""):
            """A project may close the trace, never send it somewhere else."""
            telemetry.pop("otel_endpoint", None)
        telemetry.pop("otel_headers", None)
    permissions = result.get("permissions")
    shell = result.get("shell_environment")
    ui = result.get("ui")
    if isinstance(ui, dict):
        """A project may not choose the program that runs on the machine of the user."""
        ui.pop("file_opener", None)
    result.pop("history", None)
    """The history belongs to the user: a project may neither hide it nor delete it."""
    if isinstance(shell, dict):
        """A project may hide more of the environment, never show what the user hid."""
        shell.pop("include", None)
    if not isinstance(permissions, dict):
        return result
    if str(permissions.get("mode") or "") not in TIGHT_MODES:
        permissions.pop("mode", None)
    permissions.pop("include_dirs", None)
    if str(permissions.get("network") or "") != "deny":
        """A project may close the network, never open it."""
        permissions.pop("network", None)
    rules = permissions.get("rules")
    permissions["rules"] = (
        [rule for rule in rules if isinstance(rule, dict) and str(rule.get("decision")) == "deny"]
        if isinstance(rules, list)
        else []
    )
    return result


def _entries(project: dict, section: str, key: str) -> list:
    """The entries of a section of a configuration, whatever it holds."""
    value = (project.get(section) or {}).get(key) or []
    return value if isinstance(value, list) else []


def _matchers(project: dict) -> list[dict]:
    """The hook matchers of a configuration."""
    events = (project.get("hooks") or {}).get("events") or {}
    matchers = []
    for group in events.values():
        matchers.extend(m for m in (group or []) if isinstance(m, dict))
    return matchers


def _hooks(project: dict) -> list[dict]:
    """The hooks of a configuration, whatever shape they have."""
    hooks = []
    for matcher in _matchers(project):
        hooks.extend(h for h in (matcher.get("hooks") or []) if isinstance(h, dict))
    return hooks


__all__ = [
    "DENIED",
    "TIGHT_MODES",
    "TIGHT_SANDBOX_MODES",
    "TRUSTED",
    "TRUST_FILE",
    "decision",
    "decisions",
    "is_trusted",
    "key_of",
    "project_key",
    "remember",
    "tightened",
    "trust_path",
    "waiting",
    "without_untrusted",
]
