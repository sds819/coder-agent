"""The card of a tool call: what was called, how long it took and what it returned."""

import time
from typing import Any

from textual.widgets import Static

from coderagent.ui.widgets.diff_view import colorize_diff
from coderagent.ui.widgets.markup import literal


def summarize(args: dict[str, Any]) -> str:
    """The part of the arguments that is worth showing."""
    for key in ("path", "command", "pattern", "query", "url"):
        if key in args:
            return f"{key}={args[key]}"
    return ", ".join(f"{key}={value}" for key, value in list(args.items())[:2])


def _fold(text: str, lines: int = 8) -> str:
    """The first lines of a long output; the rest is only counted."""
    rows = text.splitlines()
    if len(rows) <= lines:
        return text
    return "\n".join([*rows[:lines], f"▸ {len(rows) - lines} more lines"])


class ToolCard(Static):
    """One tool call, from the moment it starts until it is done."""

    DEFAULT_CSS = """
    ToolCard {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
    }
    """

    def __init__(self, tool: str, args: dict[str, Any], call_id: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool = tool
        self.args = args
        self.call_id = call_id
        self.started = time.time()
        self.duration = 0.0
        self.text = ""
        """What the tool returned. It is not markup."""
        self.is_error = False
        self.diff = ""

    @property
    def content(self) -> str:
        """What the tool returned. It is not markup."""
        return self.text

    @content.setter
    def content(self, text: str) -> None:
        """Set what the tool returned. The output of the tool is not markup."""
        self.text = text
        self.clear_cached_dimensions()
        self.refresh(layout=True)

    def render(self) -> str:
        summary = summarize(self.args)
        title = f"[bold]Tool: {literal(self.tool)}[/bold]" + (f" ({literal(summary)})" if summary else "")
        if not self.text:
            return f"{title}  [dim]…[/dim]"
        mark = "[red]✗[/red]" if self.is_error else "[green]✓[/green]"
        lines = [f"{title}  {mark} {self.duration * 1000:.0f}ms"]
        if self.diff:
            lines.append(colorize_diff(self.diff))
        else:
            lines.append(f"[dim]{literal(_fold(self.text))}[/dim]")
        return "\n".join(lines)

    def start(self) -> None:
        """The tool is running."""
        self.started = time.time()
        self.refresh()

    def finish(self, content: str, is_error: bool = False, diff: str = "") -> None:
        """The tool is done."""
        self.duration = time.time() - self.started
        self.content = content
        self.is_error = is_error
        self.diff = diff
        self.refresh()
