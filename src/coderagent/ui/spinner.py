"""The sign that the agent is still working.

The same dots in every interface: the terminal, the terminal interface and the
browser show the same animation, so that the user knows what it means.
"""

import sys
import threading

FRAMES = (".", "..", "...", "..")
"""The dots grow and shrink, like something that breathes."""

INTERVAL = 0.4
"""How long one frame of the animation is shown."""


def dots(step: int) -> str:
    """The dots of one moment of the animation."""
    return FRAMES[step % len(FRAMES)]


class TerminalDots:
    """The dots on a terminal that is not a window.

    The dots are written again and again on the same line, and the line is
    cleaned when the agent is done, so that the answer stands where it belongs.
    """

    def __init__(self, stream=None, enabled: bool = True) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self.enabled = enabled
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._shown = False
        """Whether the dots were written: only then is there a line to clean."""

    def start(self) -> None:
        """Show the dots, if the terminal can show them."""
        if not self.enabled or not self.stream.isatty():
            """A pipe or a file gets the answer alone; the dots would be noise in it."""
            return
        self._shown = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Take the dots away."""
        if not self._shown:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self._write("\r" + " " * len(max(FRAMES, key=len)) + "\r")
        self._shown = False

    def _run(self) -> None:
        step = 0
        while not self._stop.wait(INTERVAL):
            self._write("\r" + dots(step))
            step += 1

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()


__all__ = ["FRAMES", "INTERVAL", "TerminalDots", "dots"]
