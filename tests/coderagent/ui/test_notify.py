"""The notification the terminal shows when a turn is over."""

import sys

from coderagent.ui.notify import escape_sequence, run_notifier

NOTIFIER = """
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(sys.argv[2] + "|" + sys.argv[3], encoding="utf-8")
"""


def test_the_sequence_is_the_one_the_terminal_understands():
    assert escape_sequence("coder", "the work is done") == "\x1b]777;notify;coder;the work is done\x07"


def test_the_body_is_cut():
    assert len(escape_sequence("coder", "x" * 500)) < 300


def test_the_characters_that_would_break_the_sequence_are_gone():
    sequence = escape_sequence("coder", "a; b\nc")
    assert "\x1b]777;notify;coder;a, b c\x07" == sequence


def test_the_program_of_the_user_gets_the_title_and_the_body(tmp_path):
    """The program is called with the title and the body as its two arguments."""
    script = tmp_path / "notifier.py"
    script.write_text(NOTIFIER, encoding="utf-8")
    seen = tmp_path / "seen.txt"
    run_notifier(f"{sys.executable} {script} {seen}", "coder", "the work is done")
    assert seen.read_text(encoding="utf-8") == "coder|the work is done"


def test_a_program_that_does_not_exist_is_only_a_warning(tmp_path):
    """A broken notifier must not break the session."""
    run_notifier(f"{sys.executable} {tmp_path / 'nothing.py'}", "coder", "the work is done")


def test_an_empty_program_does_nothing():
    run_notifier("", "coder", "the work is done")
