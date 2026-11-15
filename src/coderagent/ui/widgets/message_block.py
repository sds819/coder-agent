"""A message of the conversation: what the user said, what the agent answered."""

from textual.widgets import Static

from coderagent.ui.widgets.markup import literal

ROLE_LABEL = {"user": "You", "assistant": "Agent", "command": "Command", "error": "Error", "notice": "Notice"}


class MessageBlock(Static):
    """One message. The reasoning of the agent is shown small and dim."""

    DEFAULT_CSS = """
    MessageBlock {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
    }
    """

    def __init__(self, role: str, content: str = "", reasoning: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.text = content
        """The message, as it was said. It is not markup."""
        self.reasoning = reasoning

    @property
    def content(self) -> str:
        """The message, as it was said. It is not markup."""
        return self.text

    @content.setter
    def content(self, text: str) -> None:
        """Set the message. The text of the model is not markup."""
        self.text = text
        self.clear_cached_dimensions()
        self.refresh(layout=True)

    def render(self) -> str:
        lines = [f"[bold]{ROLE_LABEL.get(self.role, self.role)}[/bold]"]
        if self.reasoning:
            lines.append(f"[dim]{literal(self.reasoning)}[/dim]")
        if self.text:
            lines.append(literal(self.text))
        return "\n".join(lines)

    def append(self, text: str) -> None:
        """Add text to the message, while it is still arriving."""
        self.text += text
        self.refresh()

    def set_content(self, text: str) -> None:
        """Set the text of the message."""
        self.text = text
        self.clear_cached_dimensions()
        self.refresh(layout=True)

    def add_reasoning(self, text: str) -> None:
        self.reasoning += text
        self.refresh()
