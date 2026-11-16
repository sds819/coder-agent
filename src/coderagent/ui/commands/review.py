"""The review of the changes: the diff as the context of a review prompt.

The review is a turn of its own: the diff goes into the prompt, so the model
looks at the changes and not at the conversation that led to them. The prompt
asks for findings and nothing else — a review does not change anything.
"""

import subprocess
from pathlib import Path

MAX_DIFF = 60000
"""The characters of the diff that go into the prompt. The rest is cut."""

REVIEW_PROMPT = """You are reviewing the changes of this project. Say what is wrong with them.

Look for:
- a bug the changes introduce, a case they do not handle
- a test that is missing for what the changes do
- a name, a comment or a docstring that does not tell the truth
- something that breaks the conventions of the project

Say where every finding is (the file and the line) and why it matters. If the
changes are fine, say so and stop. Answer with a short summary and a bullet
point per finding.

Do not change any file: this is a review, not a fix.
"""


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    """Run git and return what it says."""
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout or result.stderr).strip()


def changes(cwd: Path, revision: str = "") -> tuple[str, list[str], str]:
    """The diff of the changes, the files that are not in it, and what went wrong.

    Without a revision the changes of the working tree are reviewed, with one
    the changes of that range are (`main..HEAD`, a commit, a tag).
    """
    if revision:
        code, diff = _git(cwd, "diff", revision)
        if code != 0:
            return "", [], f"Git does not know '{revision}':\n{diff}"
    else:
        code, diff = _git(cwd, "diff", "HEAD")
        if code != 0:
            """A repository without a commit yet has no HEAD to compare with."""
            code, diff = _git(cwd, "diff")
        if code != 0:
            return "", [], f"Not a git repository: {cwd}"
    return diff, _untracked(cwd), ""


def _untracked(cwd: Path) -> list[str]:
    """The files that git does not know yet. They are part of the changes."""
    code, status = _git(cwd, "status", "--porcelain")
    if code != 0:
        return []
    return [line[3:].strip() for line in status.splitlines() if line.startswith("??")]


def prompt(diff: str, untracked: list[str], revision: str = "") -> str:
    """The prompt of the review: what to look for, and the changes themselves."""
    parts = [REVIEW_PROMPT]
    parts.append(f"The changes are the diff of `{revision}`." if revision else "The changes are the diff below.")
    if untracked:
        parts.append("These files are new and are not in the diff, read them when they matter: " + ", ".join(untracked))
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n... the diff is cut here, read the files yourself ..."
    parts.append("```diff\n" + diff + "\n```")
    return "\n\n".join(parts)
