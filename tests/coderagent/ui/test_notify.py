"""The notification the terminal shows when a turn is over."""

from coderagent.ui.notify import escape_sequence


def test_the_sequence_is_the_one_the_terminal_understands():
    assert escape_sequence("coder", "the work is done") == "\x1b]777;notify;coder;the work is done\x07"


def test_the_body_is_cut():
    assert len(escape_sequence("coder", "x" * 500)) < 300


def test_the_characters_that_would_break_the_sequence_are_gone():
    sequence = escape_sequence("coder", "a; b\nc")
    assert "\x1b]777;notify;coder;a, b c\x07" == sequence
