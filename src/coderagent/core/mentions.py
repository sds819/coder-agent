"""The files a user mentions: `@path` in a prompt and `/mention <path>`.

The content of the file goes into the message, so that the model does not have
to spend a tool call on reading it again. A file that the agent may not see
does not go into the message either: the message says that it may not be seen.
"""

import re
from pathlib import Path

from coderagent.core.redact import redact

MAX_CHARS = 20000
"""How much of a mentioned file goes into the message."""

MENTION = re.compile(r"@([^\s@]+)")
"""A mention in a prompt: an @ and a path without spaces."""

FILE_BLOCK = re.compile(r'<file path="[^"]*">.*?</file>', re.DOTALL)
"""A block of a file that is already in the message."""

TRAILING = ",;:!?)]}\"'"
"""The punctuation that ends a sentence, not a path."""


def expand(text: str, cwd: Path, policy) -> str:
    """The text with the content of the mentioned files in it.

    A name that is not a file stays as it is: `@` is used for other things
    too, in an address or in a decorator.
    """
    parts = FILE_BLOCK.split(text)
    blocks = FILE_BLOCK.findall(text)
    expanded = [MENTION.sub(lambda match: _replacement(match.group(1), cwd, policy), part) for part in parts]
    result = []
    for index, part in enumerate(expanded):
        result.append(part)
        if index < len(blocks):
            result.append(blocks[index])
    return "".join(result)


def _replacement(name: str, cwd: Path, policy) -> str:
    """What an `@name` in a prompt turns into."""
    path_text, tail = _split(name)
    content = _content(path_text, cwd, policy)
    if content is None:
        """There is no such file: the text stays as it is."""
        return f"@{name}"
    return f"{content}{tail}"


def _split(name: str) -> tuple[str, str]:
    """The path in a mention, and the punctuation that follows it."""
    stripped = name.rstrip(TRAILING)
    return stripped, name[len(stripped) :]


def _content(path_text: str, cwd: Path, policy) -> str | None:
    """The content of the file as a block. None when there is no such file."""
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = cwd / path
    if not path.is_file():
        return None
    if policy is not None and policy.check("read", {"path": str(path)}) != "allow":
        """The agent may not read this file, so the content does not go in."""
        return f'<file path="{path_text}">\nThe agent may not read this file.\n</file>'
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return f'<file path="{path_text}">\nThis file is not text.\n</file>'
    if "\x00" in text:
        """A file with a null byte in it is not a file of text."""
        return f'<file path="{path_text}">\nThis file is not text.\n</file>'
    text = redact(text)
    """The content of the file goes into the prompt and into the log of the session,
    so the secrets in it are taken out, as they are in the output of a tool."""
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n... (the rest of the file is not here)"
    return f'<file path="{path_text}">\n{text}\n</file>'
