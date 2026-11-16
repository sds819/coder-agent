"""Tell the terminal that something happened, in the way a terminal understands."""

MAX_BODY = 200
"""The characters of the notification. A terminal shows a line or two."""

TITLE = "coder"
"""The name of the program, the way the notification shows it."""


def escape_sequence(title: str, body: str) -> str:
    """The sequence OSC 777 that a terminal turns into a notification."""
    return f"\x1b]777;notify;{_clean(title)};{_clean(body)[:MAX_BODY]}\x07"


def _clean(text: str) -> str:
    """The text without the characters that would break the sequence."""
    return " ".join(text.split()).replace(";", ",")
