"""Permission modes, rules and the policy that evaluates them."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from coderagent.core.os_sandbox import FULL_ACCESS, READ_ONLY
from coderagent.tools import bash_policy

READ_TOOLS = {"read", "glob", "grep", "ls"}
WRITE_TOOLS = {"write", "edit", "multi_edit", "apply_patch"}
INFO_TOOLS = {"todo_write", "bash_output", "bash_kill"}
"""Tools that only touch the agent's own bookkeeping, so they never need approval."""
PATH_TOOLS = READ_TOOLS | WRITE_TOOLS

NETWORK_POLICIES = ("allow", "deny")
"""What the network of a session may do."""


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS = "bypass"
    READONLY = "readonly"


@dataclass
class Rule:
    tool: str = "*"
    pattern: str = "*"
    """Glob for path tools, regular expression for `bash`, tool name otherwise."""
    decision: str = "ask"
    reason: str = ""


DECISIONS = ("allow", "ask", "deny")
"""What a rule may say."""

RULE_KEYS = ("tool", "pattern", "decision", "reason")
"""The keys a rule has."""


def check_rule(rule: dict) -> None:
    """Refuse a rule that says something the policy does not know.

    A decision that is not one of the three is not a decision: the policy would
    take it for an allow, and a rule that may not deny is worse than no rule.
    """
    if not isinstance(rule, dict):
        raise ValueError(f"a rule must be a mapping, not {type(rule).__name__}.")
    unknown = set(rule) - set(RULE_KEYS)
    if unknown:
        raise ValueError(
            f"a rule has the unknown keys {', '.join(sorted(unknown))}. A rule has {', '.join(RULE_KEYS)}."
        )
    decision = str(rule.get("decision") or "ask")
    if decision not in DECISIONS:
        raise ValueError(f"a rule has the unknown decision '{decision}'. Use one of: {', '.join(DECISIONS)}.")


@dataclass
class Decision:
    decision: str
    rule: Rule | None = None
    reason: str = ""


class ApprovalDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ALWAYS = "always"


MODE_NOTES = {
    PermissionMode.PLAN: (
        "You are in plan mode. You may only look around: `read`, `glob`, `grep` and `ls` work, "
        "but every tool that changes something, `bash` included, is refused. Investigate the task "
        "and answer with the plan you would follow. The user decides whether it is executed."
    ),
    PermissionMode.READONLY: (
        "You are in read-only mode. You may only look around: `read`, `glob`, `grep` and `ls` work, "
        "but every tool that changes something, `bash` included, is refused. Answer with what you "
        "found and describe the change you would make, but do not make it."
    ),
}
"""What the model is told when the mode takes tools away from it."""


MODE_DENY_REASONS = {
    PermissionMode.PLAN: "The session is in plan mode: only looking around is allowed, changing something is not.",
    PermissionMode.READONLY: "The session is in read-only mode: nothing may be changed.",
}
"""Why the mode itself refuses a call, so that the model knows what to do instead."""


def mode_note(mode: PermissionMode) -> str:
    """The note for the model, empty when the mode needs no explanation."""
    return MODE_NOTES.get(PermissionMode(mode), "")


def mode_block(mode: PermissionMode) -> str:
    """The note as the block the model sees, empty when the mode needs no explanation."""
    note = mode_note(mode)
    if not note:
        return ""
    return f'<permission_mode mode="{PermissionMode(mode).value}">\n{note}\n</permission_mode>'


NETWORK_NOTES = {
    "deny": (
        "The network is closed. A command that reaches it is refused: no `curl`, no `wget`, no "
        "package install, no `git fetch`. Work with what is on the disk and say what you would "
        "have fetched instead."
    ),
}
"""What the model is told when the network is closed."""


def network_block(network: str) -> str:
    """The note as the block the model sees, empty when the network is open."""
    note = NETWORK_NOTES.get(network, "")
    if not note:
        return ""
    return f'<permission_network policy="{network}">\n{note}\n</permission_network>'


class Approver(Protocol):
    def request(self, tool: str, params: dict, reason: str) -> ApprovalDecision: ...


class HeadlessApprover:
    """Without a terminal there is nobody to ask, so approval-required calls are denied."""

    def __init__(self, allow: bool = False) -> None:
        self.allow = allow

    def request(self, tool: str, params: dict, reason: str) -> ApprovalDecision:
        return ApprovalDecision.ALLOW if self.allow else ApprovalDecision.DENY


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a glob into a regex where `*` does not cross `/` but `**` does."""
    parts = ["^"]
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    parts.append("$")
    return re.compile("".join(parts))


class PermissionPolicy:
    """Decides whether a tool call is allowed, needs approval or is denied."""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        rules: list[Rule] | None = None,
        *,
        cwd: Path | None = None,
        include_dirs: list[str] | None = None,
        bounded: bool = True,
        network: str = "allow",
        sandbox_mode: str = FULL_ACCESS,
        deny_paths: list[str] | None = None,
    ) -> None:
        self.mode = PermissionMode(mode)
        self.rules = list(rules or [])
        self.cwd = Path(cwd).resolve() if cwd else Path.cwd().resolve()
        self.include_dirs = [_resolve(directory, self.cwd) for directory in include_dirs or []]
        """A directory that is written down relative to the working directory."""
        self.bounded = bounded
        """Whether the commands run on this disk. A container has its own boundary."""
        if network not in NETWORK_POLICIES:
            raise ValueError(f"unknown network policy '{network}'. Use one of: {', '.join(NETWORK_POLICIES)}.")
        self.network = network
        """Whether the commands may reach the network. `deny` refuses them."""
        self.sandbox_mode = sandbox_mode
        """The mode of the operating system sandbox. `read-only` takes the write tools away."""
        self.deny_paths = list(deny_paths or [])
        """The paths that are off limits, whatever the mode says."""
        self.restriction: dict[str, str] = {}
        """The tools a command may use, and the pattern each one is limited to.

        A custom command may say `allowed-tools: bash(git diff:*)`. Then that command
        may run `git diff` and nothing else. A rule of the user cannot widen this.
        """

    def check(self, tool: str, params: dict) -> str:
        """Return `allow`, `ask` or `deny`."""
        return self.evaluate(tool, params).decision

    def evaluate(self, tool: str, params: dict) -> Decision:
        """Like `check`, but also reports which rule was hit and why."""
        reason = self._restriction_reason(tool, params)
        if reason:
            """The command may only use some tools. That holds in every mode."""
            return Decision("deny", None, reason)
        if tool == "bash":
            return self._evaluate_bash(str(params.get("command", "")))
        matched = _strictest_rule([rule for rule in self.rules if self._matches(rule, tool, params)])
        decision = matched.decision if matched else self._default_decision(tool)
        if decision not in DECISIONS:
            """A decision that is not one of the three is not a decision: ask."""
            decision = "ask"
        if tool in PATH_TOOLS:
            path = str(params.get("path", ""))
            if path and not self.within_bounds(path):
                """A rule cannot open the disk: the bounds hold in every mode."""
                return Decision("deny", matched, self._outside_reason(path))
            if self.sandbox_mode == READ_ONLY and tool in WRITE_TOOLS:
                """The sandbox is read only: a rule cannot open it either."""
                return Decision("deny", matched, "the sandbox is read only")
            denied = self.denied_path(path)
            if denied:
                """The denied paths come after the rules: they win over an allow."""
                return Decision("deny", matched, self._denied_reason(path, denied))
        reason = matched.reason if matched else ""
        if decision == "deny" and not reason:
            """A refusal without a reason leaves the model guessing."""
            reason = self._default_reason(decision)
        return Decision(decision, matched, reason)

    def _evaluate_bash(self, command: str) -> Decision:
        """The decision for a shell command.

        Every part of the command is judged on its own and the strictest part
        wins: an allowed `pytest` does not carry a `rm` along with it. A path
        that leaves the working directory is refused in every mode.
        """
        outside = bash_policy.outside_paths(command, self.cwd, self.include_dirs) if self.bounded else []
        if outside:
            """The bounds of the disk hold in every mode, like they do for the file tools."""
            return Decision("deny", None, self._outside_reason(outside[0]))
        for named in bash_policy.named_paths(command, self.cwd):
            denied = self.denied_path(named)
            if denied:
                """A denied path is off limits for the command too, not only for the file tools."""
                return Decision("deny", None, self._denied_reason(named, denied))
        if self.network == "deny":
            """The network is closed: the commands that reach it are refused."""
            for segment in bash_policy.segments(command):
                reason = bash_policy.needs_network(segment)
                if reason:
                    return Decision("deny", None, f"the network is closed: {reason}")
        if self.mode == PermissionMode.BYPASS:
            return Decision("allow", None, "")
        if self.mode in (PermissionMode.PLAN, PermissionMode.READONLY):
            return Decision("deny", None, MODE_DENY_REASONS.get(self.mode, ""))
        decision = "allow"
        rules: list[Rule] = []
        why = ""
        for segment in bash_policy.segments(command):
            rule = self._bash_rule(segment)
            if rule is not None:
                rules.append(rule)
                decision = _strictest(decision, rule.decision)
                continue
            kind, reason = bash_policy.classify_segment(segment)
            if kind in ("dangerous", "unknown"):
                decision = _strictest(decision, "ask")
                why = why or reason
        matched = _strictest_rule(rules)
        """The reason is the one of the rule that decided, or the one of the command."""
        reason = matched.reason if matched and matched.decision == decision else why
        if decision == "deny" and not reason:
            """A refusal without a reason leaves the model guessing."""
            reason = self._default_reason(decision)
        return Decision(decision, matched, reason)

    def _restriction_reason(self, tool: str, params: dict) -> str:
        """Why this call is not one of the calls the command may make."""
        if not self.restriction:
            return ""
        if tool not in self.restriction:
            return f"the command may only use {', '.join(sorted(self.restriction))}"
        pattern = self.restriction[tool]
        if pattern == "*":
            return ""
        if tool == "bash":
            for segment in bash_policy.segments(str(params.get("command", ""))):
                if not _matches_bash(pattern, segment):
                    return f"the command may only run '{pattern}'"
            return ""
        if tool in PATH_TOOLS:
            path = str(params.get("path", ""))
            if not path:
                return ""
            if glob_to_regex(pattern).match(self._relative(path)):
                return ""
            return f"the command may only touch '{pattern}'"
        return "" if pattern in ("*", tool) else f"the command may only use '{pattern}'"

    def _bash_rule(self, segment: str) -> Rule | None:
        """The rule that wins for a part of the command."""
        return _strictest_rule(
            [rule for rule in self.rules if rule.tool in ("*", "bash") and _matches_bash(rule.pattern, segment)]
        )

    def _default_decision(self, tool: str) -> str:
        if self.mode == PermissionMode.BYPASS:
            return "allow"
        if tool in READ_TOOLS | INFO_TOOLS:
            return "allow"
        if self.mode in (PermissionMode.PLAN, PermissionMode.READONLY):
            return "deny"
        if self.mode == PermissionMode.ACCEPT_EDITS:
            return "allow" if tool in WRITE_TOOLS else "ask"
        return "ask"

    def _default_reason(self, decision: str) -> str:
        """Why the call is refused when no rule had a say.

        A refusal without a reason leaves the model guessing, and it guesses
        by trying the same call again.
        """
        if decision != "deny":
            return ""
        return MODE_DENY_REASONS.get(self.mode, "") or "the rules of the session deny it."

    def _matches(self, rule: Rule, tool: str, params: dict) -> bool:
        if rule.tool not in ("*", tool):
            return False
        if tool in PATH_TOOLS:
            path = str(params.get("path", ""))
            if not path:
                return rule.pattern == "*"
            return bool(glob_to_regex(rule.pattern).match(self._relative(path)))
        return rule.pattern in ("*", tool)

    def _relative(self, path: str) -> str:
        resolved = _resolve(path, self.cwd)
        if resolved.is_relative_to(self.cwd):
            return resolved.relative_to(self.cwd).as_posix()
        return resolved.as_posix()

    def within_bounds(self, path: str) -> bool:
        """Whether a path is inside the working directory or one of the extra directories.

        The rules of the user cannot widen this: an `allow` rule for a path outside
        the bounds is still a path the agent must not touch.
        """
        resolved = _resolve(path, self.cwd)
        if resolved.is_relative_to(self.cwd):
            return True
        return any(resolved.is_relative_to(directory) for directory in self.include_dirs)

    def _outside_reason(self, path: str) -> str:
        """Why the path is refused, and where it would be allowed."""
        reason = f"'{path}' is outside the working directory {self.cwd}"
        if self.include_dirs:
            directories = ", ".join(str(directory) for directory in self.include_dirs)
            return f"{reason}. The directories that are open: {directories}"
        return reason

    def denied_path(self, path: str) -> str:
        """The pattern of a denied path that this path matches, empty when none does.

        A path matches when the pattern matches it relative to the working
        directory, when it matches the whole of it, or when it matches the name
        of the file: `*.env` is the file of the working directory as well as
        the one of any directory below it. A pattern that ends in `/**` denies
        the directory as well, so that a search below it is refused too.
        """
        if not path or not self.deny_paths:
            return ""
        relative = self._relative(path)
        name = Path(path).name
        for pattern in self.deny_paths:
            regex = glob_to_regex(pattern)
            if regex.match(relative) or regex.match(name):
                return pattern
            directory = pattern[:-3] if pattern.endswith("/**") and "*" not in pattern[:-3] else ""
            if directory and (relative == directory or relative.startswith(f"{directory}/")):
                return pattern
        return ""

    def _denied_reason(self, path: str, pattern: str) -> str:
        """Why the path is off limits."""
        return f"'{path}' is denied by the configuration ('{pattern}')"


def pattern_for(tool: str, params: dict[str, Any]) -> str:
    """The rule pattern that would allow exactly this call."""
    if tool in PATH_TOOLS:
        return str(params.get("path", "*"))
    if tool == "bash":
        """A rule is matched against a part of the command, so the rule names the first one."""
        parts = bash_policy.segments(str(params.get("command", "")))
        return re.escape(parts[0]) if parts else "*"
    return tool


def _strictest_rule(rules: list[Rule]) -> Rule | None:
    """The rule that wins among the ones that match.

    A deny is not undone by a later rule: it holds in every mode, so a rule of
    the project cannot be opened by a rule of the user. Among the other
    decisions the last rule wins, so a rule of the user overrides a rule of the
    project. A decision that is not one of the three holds as well: a rule that
    was written wrong is not undone by a later rule.
    """
    matched: Rule | None = None
    for rule in rules:
        if _holds(rule) or matched is None or not _holds(matched):
            matched = rule
    return matched


def _holds(rule: Rule) -> bool:
    """Whether the rule may not be undone by a later one."""
    return rule.decision == "deny" or rule.decision not in DECISIONS


def _matches_bash(pattern: str, segment: str) -> bool:
    """Whether the pattern of a rule is the beginning of a part of the command.

    A rule is about a command, not about a word somewhere in a line: `git push`
    does not match `echo "git push"`.
    """
    if pattern == "*":
        return True
    try:
        return bool(re.match(pattern, segment))
    except re.error:
        return False


def _resolve(path: str, base: Path) -> Path:
    """Where a path is, relative to the working directory of the session.

    A path that is written down relative is relative to the working directory
    of the session, not to the directory the process happens to stand in.
    """
    target = Path(path).expanduser()
    return (target if target.is_absolute() else base / target).resolve()


def _strictest(first: str, second: str) -> str:
    """The stricter of two decisions.

    A decision that is not one of the three is not a decision: it is an ask,
    so that a rule which was written wrong never lets a call through.
    """
    order = {"allow": 0, "ask": 1, "deny": 2}
    if order.get(first, 1) >= order.get(second, 1):
        return first if first in order else "ask"
    return second if second in order else "ask"
