"""The terminal interface.

The core of the agent knows nothing about the screen: it publishes events and the
interface listens to them. The turn itself runs in a thread, so the screen stays
alive while the model is thinking.
"""

import logging
import threading
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Tree

from coderagent.config.schema import Config
from coderagent.core.content import describe_message
from coderagent.core.events import Event, EventBus, EventType
from coderagent.core.sandbox import describe
from coderagent.core.session import SessionStore
from coderagent.run import build_loop, build_store
from coderagent.tools.permissions import ApprovalDecision
from coderagent.ui.commands import CommandContext
from coderagent.ui.commands import run as run_command
from coderagent.ui.commands.resume import resume as resume_session
from coderagent.ui.notify import TITLE, escape_sequence, run_notifier
from coderagent.ui.widgets import (
    ApprovalPrompt,
    FileTree,
    MarkdownMessage,
    MessageBlock,
    StatusBar,
    TodoPanel,
    ToolCard,
)
from coderagent.ui.widgets.diff_view import prospective_diff
from coderagent.ui.widgets.path_suggester import PathSuggester
from coderagent.ui.widgets.session_picker import SessionPicker

WRITE_TOOLS = {"write", "edit", "multi_edit", "apply_patch"}
logger = logging.getLogger("coderagent.ui")


class TUIAprover:
    """Asks the user, through the interface, whether a tool may run."""

    def __init__(self, bus: EventBus, timeout: int = 0) -> None:
        self.bus = bus
        self.timeout = timeout
        self._events: dict[str, threading.Event] = {}
        self._decisions: dict[str, ApprovalDecision] = {}
        self._counter = 0

    def request(self, tool: str, params: dict, reason: str) -> ApprovalDecision:
        """Wait until the user answers."""
        self._counter += 1
        key = str(self._counter)
        event = threading.Event()
        self._events[key] = event
        self.bus.publish(
            Event(
                type=EventType.APPROVAL_REQUEST,
                session_id="",
                timestamp=time.time(),
                payload={"id": key, "tool": tool, "params": params, "reason": reason},
            )
        )
        event.wait(self.timeout or None)
        self._events.pop(key, None)
        return self._decisions.pop(key, ApprovalDecision.DENY)

    def answer(self, key: str, decision: ApprovalDecision) -> None:
        """Give the answer of the user to the waiting tool."""
        self._decisions[key] = decision
        event = self._events.get(key)
        if event is not None:
            event.set()


class CoderApp(App):
    """The application: the conversation, the status bar and the input."""

    TITLE = "coder"
    CSS = """
    #conversation {
        height: 1fr;
        padding: 0 1;
    }
    #todos {
        dock: bottom;
    }
    #files {
        dock: left;
        width: 34;
        height: 1fr;
        border: round $panel;
        background: $panel;
    }
    """
    BINDINGS = [
        ("ctrl+c", "interrupt", "Interrupt"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+o", "sessions", "Sessions"),
        ("ctrl+t", "files", "Files"),
    ]

    def __init__(
        self,
        config: Config,
        cwd: Path,
        *,
        bus: EventBus | None = None,
        approver=None,
        session=None,
        store: SessionStore | None = None,
        loop=None,
    ) -> None:
        super().__init__()
        self.config = config
        self.cwd = Path(cwd)
        self.bus = bus or EventBus()
        self.approver = approver or TUIAprover(self.bus, config.ui.approval_timeout)
        self.store = store or build_store(config)
        self.loop = loop or build_loop(
            config, self.cwd, bus=self.bus, approver=self.approver, store=self.store, session=session
        )
        self.cards: dict[str, ToolCard] = {}
        self.current: MessageBlock | None = None
        """The message the agent is writing right now."""
        self.pending_approval: ApprovalPrompt | None = None
        self.approval_id = ""
        self.turn_running = threading.Event()
        self.interrupted = threading.Event()
        self.alive = True
        """False when the interface is gone; the events are dropped then."""
        self.history: list[str] = []
        """The messages the user sent, the oldest first."""
        self.history_index: int | None = None
        """Where in the history the user is; None is the message being written."""
        self.draft = ""
        """The message that was being written when the user went back in the history."""
        self.last_answer = ""
        """The last thing the agent said; the notification tells that much."""

    def compose(self) -> ComposeResult:
        yield FileTree(self.cwd, id="files")
        yield StatusBar(id="status")
        yield VerticalScroll(id="conversation")
        yield TodoPanel(id="todos")
        yield Input(
            placeholder="输入消息…  (/help 查看命令)",
            id="input",
            suggester=PathSuggester(self.cwd),
        )

    def on_mount(self) -> None:
        self._subscribe()
        self._update_status()
        self._say_pending()
        self.query_one("#input", Input).focus()

    def _say_pending(self) -> None:
        """Say that the project has code that is not used, so that it is no surprise."""
        from coderagent.config.loader import pending_code

        pending = pending_code(self.cwd, self.loop.context.user_home)
        if pending:
            self._add_message(
                "notice",
                f"The project has code that waits for a decision of the user: {', '.join(pending.values())}. "
                "It is not used. Run /trust to see it.",
            )

    # -- the events of the core -------------------------------------------

    def _subscribe(self) -> None:
        bus = self.loop.bus
        bus.subscribe(EventType.USER_MESSAGE, self._on_user_message)
        bus.subscribe(EventType.ASSISTANT_MESSAGE, self._on_assistant_message)
        bus.subscribe(EventType.TEXT_DELTA, self._on_text_delta)
        bus.subscribe(EventType.REASONING, self._on_reasoning)
        bus.subscribe(EventType.TOOL_CALL, self._on_tool_call)
        bus.subscribe(EventType.TOOL_RESULT, self._on_tool_result)
        bus.subscribe(EventType.APPROVAL_REQUEST, self._on_approval_request)
        bus.subscribe(EventType.STATE_CHANGE, self._on_state_change)
        bus.subscribe(EventType.ERROR, self._on_error)

    def _on_user_message(self, event: Event) -> None:
        self._ui(self._add_message, "user", describe_message(event.payload.get("content", "")))

    def _on_assistant_message(self, event: Event) -> None:
        message = event.payload.get("message") or {}
        reasoning = (message.get("extra") or {}).get("reasoning", "")
        self._ui(self._add_markdown, message.get("content", ""), reasoning)

    def _on_text_delta(self, event: Event) -> None:
        self._ui(self._append_text, event.payload.get("content", ""))

    def _on_reasoning(self, event: Event) -> None:
        self._ui(self._add_reasoning, event.payload.get("content", ""))

    def _on_tool_call(self, event: Event) -> None:
        for action in event.payload.get("actions", []):
            self._ui(self._add_card, action)

    def _on_tool_result(self, event: Event) -> None:
        payload = event.payload
        if "todos" in payload:
            self._ui(self.query_one("#todos", TodoPanel).show_todos, payload.get("todos") or [])
            return
        self._ui(self._finish_card, payload)

    def _on_approval_request(self, event: Event) -> None:
        self._ui(self._show_approval, event.payload)

    def _on_state_change(self, event: Event) -> None:
        payload = event.payload
        if payload.get("model"):
            self._ui(
                self._add_message,
                "notice",
                f"Switched from {payload.get('previous', '?')} to {payload['model']}: {payload.get('reason', '')}",
            )
        self._ui(self._update_status, payload.get("state", ""))

    def _on_error(self, event: Event) -> None:
        self._ui(self._add_message, "error", event.payload.get("error", ""))

    # -- what the interface does with them -------------------------------

    def _add_message(self, role: str, content: str, reasoning: str = "") -> None:
        if role == "assistant":
            self.last_answer = content
            """The notification tells the user what the agent said."""
        if role == "assistant" and self.current is not None:
            self.current.set_content(content)
            if reasoning:
                self.current.add_reasoning(reasoning)
            return
        block = MessageBlock(role, content, reasoning)
        self.query_one("#conversation", VerticalScroll).mount(block)
        if role == "assistant":
            self.current = block
        elif role == "user":
            self.current = None
            """The next answer of the agent is a message of its own."""
        block.scroll_visible()

    def _add_command(self, text: str) -> None:
        """The answer of a command: a block of its own, so the answer of the agent stays."""
        block = MessageBlock("command", text)
        self.query_one("#conversation", VerticalScroll).mount(block)
        block.scroll_visible()

    def _add_markdown(self, content: str, reasoning: str = "") -> None:
        """The answer of the agent, rendered as Markdown.

        The text is shown as it arrives and rendered when it is complete: half a
        code block is not worth rendering.
        """
        self.last_answer = content
        """The notification tells the user what the agent said."""
        if not self.config.ui.markdown:
            """The user asked for plain text, so the text that arrived stays."""
            self._add_message("assistant", content, reasoning)
            return
        block = MarkdownMessage(content, reasoning)
        conversation = self.query_one("#conversation", VerticalScroll)
        if self.current is not None:
            """The plain text that was shown while it arrived gives way to the Markdown."""
            conversation.mount(block, before=self.current)
            self.current.remove()
        else:
            conversation.mount(block)
        self.current = None
        block.scroll_visible()

    def _append_text(self, text: str) -> None:
        if self.current is None:
            self._add_message("assistant", "")
        self.current.append(text)

    def _add_reasoning(self, text: str) -> None:
        if self.current is None:
            self._add_message("assistant", "")
        self.current.add_reasoning(text)

    def _add_card(self, action: dict) -> None:
        card = ToolCard(action.get("tool", ""), action.get("args", {}), action.get("tool_call_id", ""))
        self.cards[card.call_id] = card
        self.query_one("#conversation", VerticalScroll).mount(card)
        card.start()

    def _finish_card(self, payload: dict) -> None:
        card = self.cards.get(payload.get("tool_call_id", ""))
        if card is None:
            return
        card.finish(payload.get("content", ""), payload.get("is_error", False), payload.get("diff", ""))

    def _show_approval(self, payload: dict) -> None:
        tool = payload.get("tool", "")
        params = payload.get("params", {})
        diff = prospective_diff(tool, params, self.cwd) if tool in WRITE_TOOLS else ""
        prompt = ApprovalPrompt(tool, params, payload.get("reason", ""), diff)
        self.pending_approval = prompt
        self.approval_id = payload.get("id", "")
        self.query_one("#conversation", VerticalScroll).mount(prompt)
        self.query_one("#input", Input).disabled = True

    def _update_status(self, state: str = "") -> None:
        bar = self.query_one("#status", StatusBar)
        context = self.loop.context
        bar.update_status(
            model=getattr(self.loop.model.backend, "model_name", self.config.model.model_name),
            tokens=context.estimated_tokens(self.loop.tools),
            window=context.config.context_window,
            cost=self.loop.session.total_cost,
            cwd=str(self.cwd),
            mode=self.loop.executor.policy.mode.value,
            state=state,
            sandbox=describe(self.loop.sandbox, self.config.sandbox.type, self.config.sandbox.mode),
        )

    def _ui(self, callback, *args) -> None:
        """Run something in the thread of the interface."""
        if not self.alive:
            return
        if self._thread_id == threading.get_ident():
            callback(*args)
            return
        try:
            self.call_from_thread(callback, *args)
        except Exception:
            logger.debug("The interface is gone, the event is dropped", exc_info=True)

    def on_unmount(self) -> None:
        """The interface is gone; the events that still come are dropped."""
        self.alive = False

    # -- the input --------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        self.history.append(text)
        self.history_index = None
        if text.startswith("/"):
            self._run_command(text)
            return
        self.run_worker(lambda: self._run_turn(text), thread=True, exclusive=True)

    def _show_history(self, key: str) -> None:
        """Walk through the messages the user sent before, the way a shell does."""
        if not self.history:
            return
        widget = self.query_one("#input", Input)
        if self.history_index is None:
            if key == "down":
                return
            self.draft = widget.value
            self.history_index = len(self.history)
        self.history_index += -1 if key == "up" else 1
        if self.history_index < 0:
            self.history_index = 0
        if self.history_index >= len(self.history):
            self.history_index = None
            widget.value = self.draft
            return
        widget.value = self.history[self.history_index]
        widget.cursor_position = len(widget.value)

    def _run_turn(self, text: str | list[dict], purpose: str = "", session=None) -> None:
        """The turn itself, in a thread."""
        self.interrupted.clear()
        self.turn_running.set()
        self.last_answer = ""
        self.loop.cancel = self.interrupted.is_set
        try:
            result = self.loop.run_turn(text, purpose, session)
        except Exception as e:
            self._ui(self._add_message, "error", f"{type(e).__name__}: {e}")
            self._notify_terminal(f"{type(e).__name__}: {e}")
            return
        finally:
            self.turn_running.clear()
        if result.stop_reason == "interrupted":
            self._ui(self._add_message, "error", "interrupted")
        elif result.error:
            self._ui(self._add_message, "error", result.error)
        self._ui(self._refresh_files)
        self._notify_terminal()

    def _notify_terminal(self, body: str = "") -> None:
        """Tell the terminal that the turn is over, in the way a terminal understands."""
        if not self.config.ui.notifications:
            return
        body = body or self.last_answer or "The turn is over."
        if not self.is_headless:
            driver = getattr(self, "_driver", None)
            if driver is not None:
                driver.write(self._notification(body))
        if self.config.ui.notify_command:
            """The program of the user tells him too, in the way he wants it."""
            run_notifier(self.config.ui.notify_command, TITLE, body)

    def _notification(self, body: str = "") -> str:
        """The sequence that tells the terminal that the turn is over."""
        return escape_sequence(TITLE, body or self.last_answer or "The turn is over.")

    def _run_command(self, line: str) -> None:
        """A slash command: quick enough to run in the interface itself."""
        if self.turn_running.is_set():
            self._add_message("error", "The agent is working. Wait for it, or press ctrl+c to stop it.")
            return
        self._add_message("user", line)
        """What the user typed is part of the conversation."""
        context = CommandContext(
            loop=self.loop,
            session=self.loop.session,
            store=self.store,
            bus=self.loop.bus,
            cwd=self.cwd,
            config=self.config,
            policy=self.loop.executor.policy,
            checkpoints=self.loop.checkpoints,
            mcp=self.loop.mcp,
            output=self._add_command,
            submit=self._submit_turn,
            submit_side=self._submit_side,
            quit=self.action_quit,
        )
        run_command(context, line)

    def _submit_turn(self, text: str | list[dict], purpose: str = "") -> None:
        """Run a turn for a command that needs the model."""
        self.run_worker(lambda: self._run_turn(text, purpose), thread=True, exclusive=True)

    def _submit_side(self, text: str, session) -> None:
        """Run a turn in a conversation that goes aside."""
        self.run_worker(lambda: self._run_turn(text, "", session), thread=True, exclusive=True)

    # -- the keys ---------------------------------------------------------

    def on_key(self, event) -> None:
        prompt = self.pending_approval
        if prompt is None:
            if event.key in ("up", "down"):
                self._show_history(event.key)
                event.stop()
            return
        if event.key in ("left", "up"):
            prompt.move(-1)
            event.stop()
            return
        if event.key in ("right", "down"):
            prompt.move(1)
            event.stop()
            return
        if event.key == " ":
            prompt.options.toggle(prompt.options.cursor)
            event.stop()
            return
        if event.key.isdigit():
            index = int(event.key) - 1
            if 0 <= index < len(prompt.options.items):
                prompt.options.toggle(index)
                event.stop()
                return
        if event.key == "enter":
            self._decide(prompt.selected_key)
            event.stop()
            return
        if event.key in ("y", "n", "a"):
            self._decide(event.key)
            event.stop()

    def _decide(self, key: str) -> None:
        """Give the answer of the user to the waiting tool."""
        decision = {"y": ApprovalDecision.ALLOW, "n": ApprovalDecision.DENY, "a": ApprovalDecision.ALWAYS}[key]
        self.pending_approval.remove()
        self.pending_approval = None
        self.approver.answer(self.approval_id, decision)
        input_widget = self.query_one("#input", Input)
        input_widget.disabled = False
        input_widget.focus()

    def action_interrupt(self) -> None:
        """Stop the turn that is running."""
        if self.turn_running.is_set():
            self.interrupted.set()
            self._add_message("error", "interrupting…")
        else:
            self.exit()

    def action_files(self) -> None:
        """Show or hide the tree of the files of the working directory."""
        tree = self.query_one("#files", FileTree)
        tree.display = not tree.display
        if tree.display:
            tree.reload()

    def _refresh_files(self) -> None:
        """Read the directory again, so that the tree tells the truth."""
        tree = self.query_one("#files", FileTree)
        if tree.display:
            tree.reload()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Put the file that was picked into the input, so it can be asked about."""
        path = event.node.data
        if not path:
            return
        widget = self.query_one("#input", Input)
        widget.value = path
        widget.focus()

    def action_sessions(self) -> None:
        """Show the sessions of this directory, so that another one can be continued."""
        if self.turn_running.is_set():
            self._add_message("error", "The agent is working. Wait for it, or press ctrl+c to stop it.")
            return
        sessions = self.store.list(self.cwd)
        if not sessions:
            self._add_message("error", "No sessions yet.")
            return
        self.push_screen(SessionPicker(sessions), self._continue_session)

    def _continue_session(self, session_id: str | None) -> None:
        """Continue the session that was picked."""
        if not session_id:
            return
        self.loop.switch_to(resume_session(self.store, session_id))
        self._show_session(session_id)
        self._update_status()
        self._add_command(f"Resumed {session_id}")

    def _show_session(self, session_id: str) -> None:
        """Show the conversation of the session, so that the screen is not a lie."""
        self.query_one("#conversation", VerticalScroll).remove_children()
        self.cards.clear()
        self.current = None
        for event in self.store.events(session_id):
            if event.type == EventType.USER_MESSAGE:
                self._add_message("user", describe_message(event.payload.get("content", "")))
            elif event.type == EventType.ASSISTANT_MESSAGE:
                self.current = None
                """Every message of the log is a message of its own."""
                self._add_markdown((event.payload.get("message") or {}).get("content", ""))

    def action_quit(self) -> None:
        """Leave, after settling the session in the memory."""
        from coderagent.run import settle

        settle(self.loop, self.config, self.cwd)
        self.exit()


def main(config: Config, cwd: Path, **kwargs) -> None:
    """Run the interface."""
    CoderApp(config, cwd, **kwargs).run()


__all__ = ["CoderApp", "TUIAprover", "main"]
