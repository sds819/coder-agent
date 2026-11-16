"""The `apply_patch` tool: a patch with context, the way Codex writes one.

    *** Begin Patch
    *** Update File: src/app.py
    @@ def main():
     the line that stays
    -the line that goes
    +the line that comes
    *** Add File: notes.md
    +a new file
    *** Delete File: old.md
    *** End Patch

The patch costs fewer tokens than the whole file, so the model sends the lines
that change and a few lines around them.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coderagent.tools.base import ToolContext, ToolResult, resolve_path
from coderagent.tools.builtin.fs import unified_diff

BEGIN = "*** Begin Patch"
END = "*** End Patch"


class PatchError(Exception):
    """The patch cannot be applied."""


@dataclass
class Hunk:
    header: str = ""
    """The text after the `@@`, a hint about where the hunk belongs."""
    lines: list[str] = field(default_factory=list)
    """The lines of the hunk, with their prefix."""


@dataclass
class FilePatch:
    action: str
    """`update`, `add` or `delete`."""
    path: str
    hunks: list[Hunk] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    """The lines of a file that is added."""


def parse_patch(text: str) -> list[FilePatch]:
    """The files the patch changes. Raises `PatchError` when the patch is malformed."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != BEGIN:
        raise PatchError(f"the patch must start with '{BEGIN}'")
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    hunk: Hunk | None = None
    ended = False
    for raw in lines[1:]:
        if raw.strip() == END:
            ended = True
            break
        if raw.startswith("*** Update File: "):
            current = FilePatch("update", raw[len("*** Update File: ") :].strip())
            patches.append(current)
            hunk = None
        elif raw.startswith("*** Add File: "):
            current = FilePatch("add", raw[len("*** Add File: ") :].strip())
            patches.append(current)
            hunk = None
        elif raw.startswith("*** Delete File: "):
            current = FilePatch("delete", raw[len("*** Delete File: ") :].strip())
            patches.append(current)
            hunk = None
        elif raw.startswith("@@"):
            if current is None or current.action != "update":
                raise PatchError("a hunk must belong to a file to update")
            hunk = Hunk(header=raw[2:].strip())
            current.hunks.append(hunk)
        elif raw.startswith(("+", "-", " ")):
            if current is None:
                raise PatchError("the patch has lines before it says which file it changes")
            if current.action == "add":
                current.lines.append(raw[1:])
            elif current.action == "update":
                if hunk is None:
                    raise PatchError(
                        "the lines of a file to update belong to a hunk, so they need a line that starts with @@"
                    )
                hunk.lines.append(raw)
            else:
                raise PatchError("a file to delete has no lines")
        elif raw.strip() == "":
            """An empty line is a line of context that has nothing in it."""
            if current is None or current.action != "update" or hunk is None:
                raise PatchError("the patch has an empty line that belongs to nothing")
            hunk.lines.append(" ")
        else:
            raise PatchError(f"unexpected line in the patch: {raw!r}")
    if not ended:
        raise PatchError(f"the patch must end with '{END}'")
    if not patches:
        raise PatchError("the patch does not change any file")
    return patches


def _hunk_parts(hunk: Hunk) -> tuple[list[str], list[str]]:
    """The lines the hunk expects and the lines it puts there."""
    old: list[str] = []
    new: list[str] = []
    for raw in hunk.lines:
        if raw.startswith("-"):
            old.append(raw[1:])
        elif raw.startswith("+"):
            new.append(raw[1:])
        else:
            text = raw[1:] if raw.startswith(" ") else raw
            old.append(text)
            new.append(text)
    return old, new


def _locate(lines: list[str], old: list[str], cursor: int, header: str) -> int | None:
    """Where the block of the hunk is in the file. None when it is not there."""
    if not old:
        return None
    candidates: list[int] = []
    if header:
        for index, line in enumerate(lines):
            if header in line:
                candidates.append(index)
                break
    candidates += [cursor, 0]
    candidates += list(range(len(lines)))
    for start in candidates:
        if start < 0 or start + len(old) > len(lines):
            continue
        if lines[start : start + len(old)] == old:
            return start
    """The file may have spaces at the end of its lines that the patch does not show."""
    stripped = [line.rstrip() for line in old]
    for start in candidates:
        if start < 0 or start + len(old) > len(lines):
            continue
        if [line.rstrip() for line in lines[start : start + len(old)]] == stripped:
            return start
    return None


def apply_to_text(original: str, patch: FilePatch) -> str:
    """The content of the file after the patch. Raises `PatchError` when it does not fit."""
    if patch.action == "add":
        return "\n".join(patch.lines) + "\n" if patch.lines else ""
    lines = original.splitlines()
    result = list(lines)
    cursor = 0
    for hunk in patch.hunks:
        old, new = _hunk_parts(hunk)
        index = _locate(result, old, cursor, hunk.header)
        if index is None:
            first = old[0].strip()[:60] if old else ""
            raise PatchError(
                f"the context of the hunk does not match {patch.path}: '{first}' is not where the patch says it is. "
                "Read the file again and use the lines that are really there."
            )
        result[index : index + len(old)] = new
        cursor = index + len(new)
    text = "\n".join(result)
    if original.endswith("\n") or not original:
        text += "\n"
    return text


def touched_paths(patch_text: str) -> list[str]:
    """The files the patch touches. Empty when the patch cannot be read."""
    try:
        return [patch.path for patch in parse_patch(patch_text)]
    except PatchError:
        return []


def preview(patch_text: str, cwd: Path) -> str:
    """The diff the patch would make, without changing anything."""
    try:
        patches = parse_patch(patch_text)
    except PatchError:
        return ""
    diffs = []
    for patch in patches:
        target = Path(patch.path)
        if not target.is_absolute():
            target = cwd / target
        before = target.read_text(encoding="utf-8") if target.is_file() else ""
        try:
            after = apply_to_text(before, patch)
        except PatchError:
            continue
        if before != after:
            diffs.append(unified_diff(before, after, patch.path))
    return "\n".join(diffs)


class ApplyPatchTool:
    name = "apply_patch"
    description = (
        "Apply a patch to the files of the working directory. The patch looks like this: "
        "'*** Begin Patch', then '*** Update File: path' with hunks that start with '@@', the lines that stay "
        "(with a space), the lines that go (with a -) and the lines that come (with a +), then "
        "'*** Add File: path' with the lines of the new file and '*** Delete File: path'. "
        "It ends with '*** End Patch'. A patch costs fewer tokens than the whole file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "patch": {"type": "string", "description": "The patch to apply."},
        },
        "required": ["patch"],
    }

    def run(self, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        patch_text = params.get("patch")
        if not isinstance(patch_text, str) or not patch_text.strip():
            return ToolResult("Error: `patch` is required and must be a non-empty string.", is_error=True)
        try:
            patches = parse_patch(patch_text)
        except PatchError as error:
            return ToolResult(f"Error: {error}", is_error=True)

        changes: list[tuple[Path, str, str]] = []
        """The file, what it was and what it becomes."""
        for patch in patches:
            target = resolve_path(ctx, patch.path)
            if not ctx.policy.within_bounds(str(target)):
                return ToolResult(
                    f"Error: '{patch.path}' is outside the working directory {ctx.policy.cwd}.",
                    is_error=True,
                )
            if patch.action == "delete":
                if not target.exists():
                    return ToolResult(f"Error: file not found: {patch.path}.", is_error=True)
                changes.append((target, target.read_text(encoding="utf-8"), ""))
                continue
            if patch.action == "add" and target.exists():
                return ToolResult(f"Error: the file {patch.path} exists already.", is_error=True)
            if patch.action == "update" and not target.exists():
                return ToolResult(f"Error: file not found: {patch.path}.", is_error=True)
            before = target.read_text(encoding="utf-8") if target.exists() else ""
            try:
                after = apply_to_text(before, patch)
            except PatchError as error:
                return ToolResult(f"Error: {error}", is_error=True)
            changes.append((target, before, after))

        for target, _, after in changes:
            if after == "" and target.exists():
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(after, encoding="utf-8", newline="")

        names = [
            str(target.relative_to(ctx.cwd)) if target.is_relative_to(ctx.cwd) else str(target)
            for target, _, _ in changes
        ]
        diffs = [
            unified_diff(before, after, name)
            for (target, before, after), name in zip(changes, names)
            if before != after
        ]
        return ToolResult(
            f"Applied the patch to {len(changes)} file(s): {', '.join(names)}",
            metadata={"diff": "\n".join(diffs), "paths": [str(target) for target, _, _ in changes]},
        )

    def touched_paths(self, params: dict[str, Any]) -> list[str]:
        """The files the patch touches, so that they get a checkpoint."""
        patch_text = params.get("patch")
        return touched_paths(patch_text) if isinstance(patch_text, str) else []
