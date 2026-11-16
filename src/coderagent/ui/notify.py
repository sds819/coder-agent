"""Tell the terminal that something happened, in the way a terminal understands."""

import logging
import shlex
import subprocess

logger = logging.getLogger("coderagent.ui.notify")

MAX_BODY = 200
"""The characters of the notification. A terminal shows a line or two."""

TITLE = "coder"
"""The name of the program, the way the notification shows it."""

NOTIFY_TIMEOUT = 10
"""The seconds the program of the user may take."""


def escape_sequence(title: str, body: str) -> str:
    """The sequence OSC 777 that a terminal turns into a notification."""
    return f"\x1b]777;notify;{_clean(title)};{_clean(body)[:MAX_BODY]}\x07"


def run_notifier(command: str, title: str, body: str) -> None:
    """Tell the user with the program of their choice that the turn is over.

    The program gets the title and the body as its two arguments. A program
    that fails is a warning, never a broken session.
    """
    parts = shlex.split(command)
    if not parts:
        return
    try:
        subprocess.run(  # noqa: S603
            [*parts, title, body],
            timeout=NOTIFY_TIMEOUT,
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("The notifier did not run: %s", error)


def _clean(text: str) -> str:
    """The text without the characters that would break the sequence."""
    return " ".join(text.split()).replace(";", ",")
