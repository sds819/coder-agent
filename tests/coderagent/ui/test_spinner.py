"""The sign that the agent is still working."""

import time

from coderagent.ui import spinner
from coderagent.ui.spinner import FRAMES, TerminalDots, dots


class FakeTerminal:
    """A terminal that writes down what it is given."""

    def __init__(self, tty: bool = True) -> None:
        self.tty = tty
        self.text = ""

    def isatty(self) -> bool:
        return self.tty

    def write(self, text: str) -> None:
        self.text += text

    def flush(self) -> None:
        pass


def test_the_dots_grow_and_shrink():
    assert [dots(step) for step in range(len(FRAMES))] == list(FRAMES)
    assert dots(len(FRAMES)) == dots(0)


def test_the_dots_are_written_on_one_line_and_cleaned(monkeypatch):
    monkeypatch.setattr(spinner, "INTERVAL", 0.01)
    terminal = FakeTerminal()
    signs = TerminalDots(stream=terminal)
    signs.start()
    time.sleep(0.1)
    signs.stop()

    assert "\r." in terminal.text
    """Every frame of the animation is written on the same line."""
    assert terminal.text.count("\r") >= 2
    assert terminal.text.endswith("\r   \r")
    """The line is cleaned, so that the answer of the agent stands where it belongs."""


def test_a_pipe_gets_no_dots(monkeypatch):
    """A file or a pipe gets the answer alone."""
    monkeypatch.setattr(spinner, "INTERVAL", 0.01)
    terminal = FakeTerminal(tty=False)
    signs = TerminalDots(stream=terminal)
    signs.start()
    time.sleep(0.05)
    signs.stop()

    assert terminal.text == ""


def test_the_dots_can_be_turned_off():
    """The output for a machine is not mixed with the animation."""
    terminal = FakeTerminal()
    signs = TerminalDots(stream=terminal, enabled=False)
    signs.start()
    time.sleep(0.05)
    signs.stop()

    assert terminal.text == ""
