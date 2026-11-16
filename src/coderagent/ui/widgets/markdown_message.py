"""A message of the agent, rendered as Markdown.

The text arrives piece by piece, so it is shown as it comes. When the answer is
complete it is rendered as Markdown: the code blocks, the tables and the lists
look the way they look in the README of a project.
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Markdown, Static

from coderagent.ui.widgets.markup import literal


class MarkdownMessage(Vertical):
    """The answer of the agent, with its Markdown rendered."""

    DEFAULT_CSS = """
    MarkdownMessage {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;

        Markdown {
            padding: 0;
        }
    }
    """

    def __init__(self, content: str = "", reasoning: str = "", label: str = "Agent", **kwargs) -> None:
        super().__init__(**kwargs)
        self.content = content
        """The answer, as it was said."""
        self.reasoning = reasoning
        self.label = label

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.label}[/bold]")
        if self.reasoning:
            yield Static(f"[dim]{literal(self.reasoning)}[/dim]")
        yield Markdown(self.content)


__all__ = ["MarkdownMessage"]
