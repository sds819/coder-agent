"""The dots that say the agent is still working."""

from textual.widgets import Static

from coderagent.ui.spinner import INTERVAL, dots


class WorkingDots(Static):
    """The sign that the agent has not answered yet."""

    DEFAULT_CSS = """
    WorkingDots {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
    }
    """

    def on_mount(self) -> None:
        self.step = 0
        self._timer = self.set_interval(INTERVAL, self._tick)

    def _tick(self) -> None:
        """The next frame of the animation."""
        self.step += 1
        self.update(f"[dim]{dots(self.step)}[/dim]")
