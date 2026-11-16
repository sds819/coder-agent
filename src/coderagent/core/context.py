"""The context engine: assembles what the model sees and decides when to compact.

The order is fixed: the system prompt, the project instructions and the task list,
the summary of the compacted part, and then the history. The summary comes before
the history because it is the older part of the conversation.

The history holds everything since the last compaction. Compaction replaces the
older part of it with a structured summary, so nothing is ever dropped silently.
"""

import time
from functools import partial
from pathlib import Path

from coderagent.config.schema import ContextConfig, MemoryConfig
from coderagent.core.budget import BudgetGuard, context_window_for
from coderagent.core.events import Event, EventBus, EventType
from coderagent.core.history import History
from coderagent.core.instructions import InstructionBlock, load_instructions, once_per_file, subdirectory_instructions
from coderagent.core.memory import load_project_memory, load_user_memory
from coderagent.core.os_sandbox import sandbox_block
from coderagent.core.session import Session, SessionStore
from coderagent.core.summarize import (
    Summary,
    chunk_messages,
    conservative_summary,
    merge_prompt,
    merge_summaries,
    parse_summary,
    recent_errors,
    summarize_prompt,
)
from coderagent.core.tokens import estimate_tokens
from coderagent.tools.permissions import PermissionPolicy, mode_block, network_block

SUMMARY_OVERHEAD = 2000
"""The tokens the prompt template and the answer of a summary take."""

MISSING_RESULT = "Error: the tool call was not finished: the session ended before its result was recorded."
"""What a tool call that never came back says."""


def repair_tool_calls(messages: list[dict]) -> list[dict]:
    """Give every tool call a result, even the ones that never came back.

    A session that was killed between the answer of the model and the result of
    a tool has a tool call without a result, and a provider refuses such a
    history: the session could not be continued. The missing result is a tool
    message that says the call was not finished.

    The history itself is left as it is: the event log is the truth, and the
    repair is what the model is shown.
    """
    repaired: list[dict] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        repaired.append(message)
        index += 1
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant" or not calls:
            continue
        group: list[dict] = []
        while index < len(messages) and messages[index].get("role") == "tool":
            group.append(messages[index])
            index += 1
        answered = {tool.get("tool_call_id"): tool for tool in group}
        for call in calls:
            repaired.append(answered.get(call.get("id")) or _missing_result(call))
        known = {call.get("id") for call in calls}
        repaired.extend(tool for tool in group if tool.get("tool_call_id") not in known)
    return repaired


def _missing_result(call: dict) -> dict:
    """The result of a tool call that was never finished."""
    return {"role": "tool", "tool_call_id": call.get("id", ""), "content": MISSING_RESULT}


class ContextEngine:
    def __init__(
        self,
        session: Session,
        store: SessionStore,
        bus: EventBus,
        config: ContextConfig,
        model,
        *,
        system_prompt: str = "",
        instructions: list[InstructionBlock] | None = None,
        memory_config: MemoryConfig | None = None,
        summary_model=None,
        cwd: Path | None = None,
        user_home: Path | None = None,
        policy: PermissionPolicy | None = None,
        hooks=None,
    ) -> None:
        self.session = session
        self.store = store
        self.bus = bus
        self.config = config
        self.model = model
        self.summary_model = summary_model or model
        self.system_prompt = system_prompt
        self.cwd = Path(cwd) if cwd else session.cwd
        self.user_home = user_home
        self.policy = policy
        """The permission policy. It is shared, so the mode can change under us."""
        self.hooks = hooks
        """The hook runner, when the session has hooks."""
        self.history = History()
        self.summaries: list[Summary] = []
        self.instruction_blocks: list[InstructionBlock] = list(instructions or [])
        """The instructions of the subdirectories, and the ones the caller gave."""
        self.reload_instructions = instructions is None
        """Whether the instruction files are read again every round.

        The project may change its AGENTS.md while the session runs, and then the
        model has to see the new one.
        """
        self.memory_config = memory_config or MemoryConfig()
        self.guard = BudgetGuard(
            context_window=config.context_window,
            reserved_output=config.reserved_output,
            compact_threshold=config.compact_threshold,
        )
        self.last_compact_turn = 0

    @property
    def summary(self) -> Summary | None:
        """The most recent summary. Older ones are kept as well."""
        return self.summaries[-1] if self.summaries else None

    # -- history ---------------------------------------------------------

    def restore(self) -> None:
        """Rebuild the history and the summaries from the event log."""
        messages: list[dict] = []
        summaries: list[Summary] = []
        for event in self.store.events(self.session.id):
            payload = event.payload
            if event.type == EventType.USER_MESSAGE:
                messages.append({"role": "user", "content": payload.get("content", "")})
            elif event.type == EventType.ASSISTANT_MESSAGE:
                messages.append(payload.get("message", {}))
            elif event.type == EventType.TOOL_RESULT:
                messages.extend(payload.get("messages", []))
            elif event.type == EventType.COMPACTION:
                messages = messages[payload.get("compacted_messages", 0) :]
                summaries = [Summary.from_dict(item) for item in payload.get("summaries", [])]
            elif event.type == EventType.REVERTED:
                messages = messages[: payload.get("messages", len(messages))]
        self.history = History(messages)
        self.summaries = summaries

    def append(self, message: dict, original: str = "") -> None:
        """Add a message to the history and record it in the event log.

        `original` is what the user typed, when a hook rewrote the prompt. The
        log keeps the prompt the model saw, so that a replay says the same
        thing, and the original beside it.
        """
        self.history.append(message)
        self._record(message, original)

    def extend(self, messages: list[dict]) -> None:
        """Add tool results to the history and record them in the event log."""
        self.history.extend(messages)
        for message in messages:
            self._record(message)

    def _record(self, message: dict, original: str = "") -> None:
        """The event log is the source of truth, so every message goes into it."""
        role = message.get("role")
        if role == "user":
            event_type = EventType.USER_MESSAGE
            payload = {"content": message.get("content", "")}
            if original:
                payload["original"] = original
        elif role == "assistant":
            event_type = EventType.ASSISTANT_MESSAGE
            payload = {"message": message, "cost": message.get("extra", {}).get("cost", 0.0)}
        elif role == "tool":
            event_type = EventType.TOOL_RESULT
            payload = {"messages": [message], "todos": self.session.metadata.get("todos", [])}
        else:
            return
        event = Event(type=event_type, session_id=self.session.id, timestamp=time.time(), payload=payload)
        self.bus.publish(event)
        self.store.append(self.session.id, event)

    # -- assembly --------------------------------------------------------

    def build_messages(self, *, tools: list[dict] | None = None) -> list[dict]:
        """The messages to send to the model."""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        mode = self._policy_text()
        if mode:
            messages.append({"role": "user", "content": mode})
        instructions = self._instruction_text()
        if instructions:
            messages.append({"role": "user", "content": instructions})
        summary = self._summary_text()
        if summary:
            messages.append({"role": "user", "content": summary})
        messages.extend(repair_tool_calls(self.history.messages))
        return messages

    def _policy_text(self) -> str:
        """What the model is told when the permissions take something away from it.

        The mode and the network change while the session runs, so this is read
        every time the messages are built and never baked into the system prompt.
        """
        if self.policy is None:
            return ""
        return "\n\n".join(
            text
            for text in (
                mode_block(self.policy.mode),
                network_block(self.policy.network),
                sandbox_block(self.policy.sandbox_mode),
            )
            if text
        )

    def estimated_tokens(self, tools: list[dict] | None = None) -> int:
        """The size of the whole context. This is what the budget is checked against."""
        return estimate_tokens(self.build_messages(tools=tools), tools)

    def _instruction_text(self) -> str:
        """The instructions and the memory, one block per file.

        The file of the user is both an instruction and a memory, so it is read
        twice and shown once. The memory wins: it is read again every round.
        """
        blocks = list(self.instruction_blocks)
        if self.reload_instructions:
            """The instruction files are read again, so a change of the project counts."""
            blocks = load_instructions(self.cwd, self.user_home, self.config.project_doc_max_bytes) + blocks
        if self.memory_config.enabled:
            blocks += load_project_memory(self.cwd, self.memory_config)
            user_memory = load_user_memory(self.memory_config, self.user_home)
            if user_memory:
                blocks.append(user_memory)
        todos = self.session.metadata.get("todos") or []
        parts = [block.render() for block in once_per_file(blocks)]
        if todos:
            lines = [
                f"- [{'x' if todo.get('status') == 'completed' else ' '}] {todo.get('content', '')}" for todo in todos
            ]
            parts.append("<current_todos>\n" + "\n".join(lines) + "\n</current_todos>")
        return "\n\n".join(parts)

    def _summary_text(self) -> str:
        if not self.summaries:
            return ""
        if len(self.summaries) == 1:
            return self.summaries[0].render()
        parts = [summary.render() for summary in self.summaries]
        return "\n\n".join(parts)

    # -- compaction ------------------------------------------------------

    def maybe_compact(self) -> bool:
        """Compact when the context is close to the limit. Returns whether it happened."""
        if not self.config.auto_compact:
            return False
        if self.guard.should_compact(self.estimated_tokens()):
            return self.compact()
        if (
            self.config.compact_every_turns
            and self.session.turn_count - self.last_compact_turn > self.config.compact_every_turns
        ):
            return self.compact()
        return False

    def force_compact(self) -> bool:
        """Compact regardless of the budget. Used when the provider says the context is too big."""
        return self.compact()

    def compact(self) -> bool:
        """Replace the older part of the history with a summary."""
        cut = self._cut_index()
        if cut <= 0:
            return False
        compacted = self.history.messages[:cut]
        if self.hooks:
            """The hooks see what is about to be compressed, and then the summary."""
            self.hooks.apply("PreCompact", {"messages": compacted, "turn": self.session.turn_count})
        before = getattr(self.summary_model, "total_cost", 0.0)
        summary = self._summarize(compacted)
        cost = getattr(self.summary_model, "total_cost", 0.0) - before
        if self.summary_model is not self.model:
            """The summary ran on its own model, so its cost is booked on the main one."""
            self.model.total_cost = getattr(self.model, "total_cost", 0.0) + cost
        self.summaries = [summary]
        self.history.messages = self.history.messages[cut:]
        self.last_compact_turn = self.session.turn_count
        source_tokens = estimate_tokens(compacted)
        summary_tokens = estimate_tokens([{"role": "user", "content": summary.render()}])
        if self.hooks:
            self.hooks.apply(
                "PostCompact",
                {
                    "summary": summary.render(),
                    "messages": cut,
                    "tokens": source_tokens,
                    "summary_tokens": summary_tokens,
                },
            )
        event = Event(
            type=EventType.COMPACTION,
            session_id=self.session.id,
            timestamp=time.time(),
            payload={
                "compacted_messages": cut,
                "tokens": source_tokens,
                "summary_tokens": summary_tokens,
                "summary_ratio": round(summary_tokens / source_tokens, 4) if source_tokens else 0.0,
                "cost": cost,
                "summary": summary.to_dict(),
                "summaries": [item.to_dict() for item in self.summaries],
            },
        )
        self.bus.publish(event)
        self.store.append(self.session.id, event)
        return True

    def _cut_index(self) -> int:
        """Where the kept window starts. Always a turn boundary.

        Two rules decide how much is kept: the last `keep_recent_turns` turns, and
        enough tokens to fill `keep_recent_token_ratio` of the context window. The
        larger of the two wins, so a few huge turns are kept as well as many small ones.
        """
        messages = self.history.messages
        starts = self.history.turn_starts()
        if not starts:
            return 0
        candidates = [0, *starts]
        earliest = starts[max(0, len(starts) - self.config.keep_recent_turns)]
        if earliest == 0:
            return 0
        budget = int(self.config.context_window * self.config.keep_recent_token_ratio)
        cut = earliest
        for index in candidates:
            if index <= earliest and estimate_tokens(messages[index:]) >= budget:
                cut = index
        limit = self.guard.limit() - estimate_tokens(self._summary_messages())
        while cut < len(messages) and estimate_tokens(messages[cut:]) > limit:
            later = [index for index in candidates if index > cut]
            if not later:
                break
            cut = later[0]
        return cut

    def _summary_messages(self) -> list[dict]:
        text = self._summary_text()
        return [{"role": "user", "content": text}] if text else []

    def _summarize(self, messages: list[dict]) -> Summary:
        """Summarize the compacted part.

        A history that does not fit into one prompt is summarized in chunks, and
        the partial summaries are merged into one. The previous summary goes in
        as well, so that a second compaction does not lose what the first one found.
        """
        previous = self.summaries[-1] if self.summaries else None
        chunks = chunk_messages(messages, self._summary_limit())
        if len(chunks) <= 1:
            payload = list(chunks[0]) if chunks else []
            if previous:
                payload.append({"role": "user", "content": previous.render()})
            summary = self._ask(summarize_prompt, payload, _writes(messages)) or conservative_summary(payload)
        else:
            parts = [
                self._ask(summarize_prompt, chunk, _writes(chunk)) or conservative_summary(chunk) for chunk in chunks
            ]
            summary = self._ask(partial(merge_prompt, previous=self._summary_text()), parts, _writes(messages)) or (
                merge_summaries([previous, *parts] if previous else parts)
            )
        summary.recent_errors = recent_errors(messages)
        return summary

    def _ask(self, prompt, payload, expect_files: bool) -> Summary | None:
        """Ask the model for a summary. None when it does not deliver a usable one."""
        for _ in range(2):
            try:
                text = self.summary_model.complete([{"role": "user", "content": prompt(payload)}])
            except Exception:
                continue
            summary = parse_summary(text)
            if summary is not None and (summary.files_touched or not expect_files):
                return summary
        return None

    def _summary_limit(self) -> int:
        """How many tokens the summarizer may take in one prompt."""
        if self.config.summary_chunk_tokens:
            return self.config.summary_chunk_tokens
        window = self.config.context_window
        name = getattr(getattr(self.summary_model, "backend", None), "model_name", "")
        if name:
            window = context_window_for(name, default=window)
        return max(1000, window - self.config.reserved_output - SUMMARY_OVERHEAD)

    def rewind_to(self, messages: int) -> int:
        """Drop the messages after a checkpoint. Returns how many were dropped."""
        messages = max(0, min(messages, len(self.history.messages)))
        dropped = len(self.history.messages) - messages
        self.history.messages = self.history.messages[:messages]
        event = Event(
            type=EventType.REVERTED,
            session_id=self.session.id,
            timestamp=time.time(),
            payload={"messages": messages},
        )
        self.bus.publish(event)
        self.store.append(self.session.id, event)
        return dropped

    def note_path(self, path: str) -> None:
        """Remember the instruction files of a directory the agent just touched."""
        if not path:
            return
        target = Path(path)
        if not target.is_absolute():
            target = self.cwd / target
        known = {block.path for block in self.instruction_blocks}
        for block in subdirectory_instructions(target, self.cwd, self.config.project_doc_max_bytes):
            if block.path not in known:
                self.instruction_blocks.append(block)
                known.add(block.path)


def _writes(messages: list[dict]) -> bool:
    """Whether the messages contain a call that changed a file."""
    return any(
        call.get("function", {}).get("name") in ("write", "edit", "multi_edit", "apply_patch")
        for message in messages
        for call in message.get("tool_calls") or []
    )
