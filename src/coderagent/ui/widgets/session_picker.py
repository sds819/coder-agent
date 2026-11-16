"""A panel to pick another session of this directory."""

import time

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static

from coderagent.core.session import Session


class SessionPicker(ModalScreen[str | None]):
    """The sessions of this directory; the one that is picked is the one to continue."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    SessionPicker {
        align: center middle;
    }
    SessionPicker > Vertical {
        width: 70%;
        height: 60%;
        border: round $accent;
        background: $surface;
    }
    """

    def __init__(self, sessions: list[Session]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("The sessions of this directory. Enter continues it, escape closes.")
            yield OptionList(*(self.label(session) for session in self.sessions), id="sessions")

    def on_mount(self) -> None:
        self.query_one("#sessions", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.sessions[event.option_index].id)

    @staticmethod
    def label(session: Session) -> str:
        """The line of a session in the list."""
        when = time.strftime("%m-%d %H:%M", time.localtime(session.updated_at))
        return f"{session.id}  {session.turn_count:>3} turns  {when}"
