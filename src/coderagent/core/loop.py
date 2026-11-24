"""The main loop: user input -> model -> tools -> model, until the model stops."""

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from coderagent.config.schema import ContextConfig
from coderagent.core import schema
from coderagent.core.content import text_of, with_text
from coderagent.core.context import ContextEngine
from coderagent.core.events import Event, EventBus, EventType
from coderagent.core.mentions import expand as expand_mentions
from coderagent.core.otel import build_trace
from coderagent.core.protocols import ToolExecutor
from coderagent.core.session import Session, SessionState, SessionStore
from coderagent.core.tokens import trim_text
from coderagent.models.gateway import ModelGateway, is_context_overflow
from coderagent.models.streaming import ModelEvent, message_from_events
from coderagent.tools.permissions import PermissionMode
from minisweagent.environments.local import LocalEnvironment

logger = logging.getLogger("coderagent.core.loop")

VERIFY_OUTPUT_TOKENS = 2000
"""The tokens of the output of a check that go back to the model."""

MAX_SCHEMA_ATTEMPTS = 2
"""How many answers the model may give for a schema. Two means: one answer and one try again."""

REVIEW_NOTE = "[the changes that were reviewed are not in the context anymore: read the files again]"
"""What takes the place of the diff of a review when the turn is over."""

STOP_NOTES = {
    "max_turns": "the turn was cut off: it reached the ceiling of {max_turns} model calls",
    "cost_exceeded": "the turn stopped: the budget of the session is spent",
    "token_limit": "the turn stopped: the token limit of the session is reached",
}
"""What to say when a turn did not end the way a turn should.

A turn that ends like this has not failed, but it has not finished either: the
user has to know why the agent went quiet.
"""


def stop_note(stop_reason: str, max_turns: int = 0) -> str:
    """The line that tells the user why the turn stopped. Empty when it ended well."""
    note = STOP_NOTES.get(stop_reason, "")
    return note.format(max_turns=max_turns) if note else ""


def _answer_of(messages: list[dict]) -> str:
    """What the agent answered."""
    for message in reversed(messages):
        if message.get("role") == "assistant":
            return text_of(message.get("content"))
    return ""


class Interrupted(Exception):
    """The turn was stopped while the model was answering."""


@dataclass
class TurnResult:
    session_id: str
    turn_count: int
    """Number of user-initiated turns in this session so far."""
    cost: float
    """What this turn cost."""
    stop_reason: str
    """One of `end_turn`, `max_turns`, `cost_exceeded`, `token_limit`, `schema_invalid`, `error`."""
    messages: list[dict] = field(default_factory=list)
    """Messages added during this turn."""
    error: str = ""
    """Why the turn stopped, if it stopped because of an error."""
    session_cost: float = 0.0
    """What the whole session cost, the turns before this one and the reflection included."""
    output: Any = None
    """The answer of the agent, when a schema was asked for. None otherwise."""


class AgentLoop:
    def __init__(
        self,
        model: ModelGateway,
        executor: ToolExecutor,
        session: Session,
        store: SessionStore,
        bus: EventBus,
        *,
        context: ContextEngine | None = None,
        tools: list[dict] | None = None,
        system_prompt: str = "",
        max_turns: int = 100,
        cost_limit: float = 0.0,
        token_limit: int = 0,
        checkpoints=None,
        hooks=None,
        mcp=None,
        subagents=None,
        router=None,
        plugins=None,
        sandbox=None,
        schema_budget: int | None = None,
        verify=None,
        exporter=None,
        output_schema: dict | None = None,
        enforce_ceilings: bool = False,
    ) -> None:
        self.model = model
        self.executor = executor
        self.policy = executor.policy
        """The permission policy of the session. `/mode` changes it under us."""
        self.session = session
        self.store = store
        self.bus = bus
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.cost_limit = cost_limit
        self.token_limit = token_limit
        """Stop after this many tokens. The budget of a model that has no price."""
        self.enforce_ceilings = enforce_ceilings
        """Whether the ceilings hold even in bypass. A harness that measures asks for them."""
        self.checkpoints = checkpoints
        self.hooks = hooks
        """The hook runner, when the session has hooks."""
        self.mcp = mcp
        """The MCP manager, when the session has servers."""
        self.subagents = subagents or {}
        """The sub agents that are available, by name."""
        self.router = router
        """The model router, when the session has one."""
        self.plugins = plugins or []
        """The plugins that were loaded, by name."""
        self.sandbox = sandbox
        """The environment the commands run in."""
        self.schema_budget = schema_budget
        """The tokens the schemas of the tools may take. None means no limit."""
        self.verify = verify
        """The commands that check the work of the agent. None means: no verification."""
        self.exporter = exporter
        """Where the trace of the session goes. None means: it stays in the event log."""
        self.output_schema = output_schema
        """The shape the answer of the agent has to have. None means: any shape is fine."""
        self._exported = 0
        """How many events of the session the backend has seen."""
        self.cancel = None
        """A callable that says whether the turn should stop. The interface sets it."""
        self.purpose = "main"
        """Why the model is called. The router picks the model of the purpose."""
        self._warned_unpriced = False
        self.context = context or ContextEngine(
            session,
            store,
            bus,
            ContextConfig(),
            model,
            system_prompt=system_prompt,
            cwd=session.cwd,
            policy=self.policy,
        )
        self.context.system_prompt = self._system_prompt(system_prompt or self.context.system_prompt)
        self.context.hooks = self.hooks
        """The context needs the hooks too: it is the one that compresses."""
        self.context.tools = self.tools
        """The schemas of the tools are in every request, so the budget counts them."""
        self.context.restore()
        self._session_start()

    @property
    def messages(self) -> list[dict]:
        return self.context.history.messages

    def _system_prompt(self, base: str) -> str:
        """The prompt of the model, with the shape its answer has to have."""
        if not self.output_schema:
            return base
        return f"{base}\n\n{schema.note(self.output_schema)}".strip()

    def switch_to(self, session: Session, *, start: bool = True) -> None:
        """Continue in another session, with the history that session already has."""
        self.session = session
        self.context = ContextEngine(
            session,
            self.store,
            self.bus,
            self.context.config,
            self.model,
            system_prompt=self.system_prompt,
            memory_config=self.context.memory_config,
            summary_model=self.context.summary_model,
            cwd=session.cwd,
            policy=self.policy,
            instructions=self.context.instruction_blocks,
            user_home=self.context.user_home,
        )
        self.context.reload_instructions = True
        """The instruction files of the new directory are read again."""
        self.context.system_prompt = self._system_prompt(self.context.system_prompt)
        """The shape of the answer is told again: the new context starts from scratch."""
        self.context.hooks = self.hooks
        self.context.tools = self.tools
        self.context.restore()
        self._exported = 0
        """Another session has its own trace."""
        if start:
            self._session_start()

    def run(self, user_input: str | list[dict]) -> TurnResult:
        """Alias for `run_turn`; the caller drives the conversation."""
        return self.run_turn(user_input)

    def run_turn(self, user_input: str | list[dict], purpose: str = "", session: Session | None = None) -> TurnResult:
        """Run one turn: query the model, execute its tool calls, repeat until it stops.

        The input is a string, or the parts of a message that carries images.
        The purpose says which model answers the turn: `main` unless the caller
        says otherwise, like `review`. A session says that the turn happens
        somewhere else: a conversation that goes aside.
        """
        if session is None:
            return self._turn(user_input, purpose)
        return self._aside(user_input, purpose, session)

    def _aside(self, user_input: str | list[dict], purpose: str, session: Session) -> TurnResult:
        """Run a turn in another session, and come back to this one.

        The conversation that goes aside has its own log. This one is not
        touched: the question and the answer are recorded in it, and nothing else.
        """
        previous = self.session
        exported = self._exported
        self.switch_to(session)
        try:
            result = self._turn(user_input, purpose or "side")
        finally:
            self.switch_to(previous, start=False)
            self._exported = exported
        self.session.total_cost += result.cost
        """The user paid for the side conversation, so the session pays for it."""
        self._publish(
            EventType.SIDE_CONVERSATION,
            {
                "question": text_of(user_input),
                "answer": _answer_of(result.messages),
                "session_id": session.id,
                "cost": result.cost,
                "stop_reason": result.stop_reason,
            },
        )
        return result

    def _turn(self, user_input: str | list[dict], purpose: str = "") -> TurnResult:
        self.purpose = purpose or "main"
        turn_messages: list[dict] = []
        prompt = user_input
        original = ""
        if self.hooks:
            hook = self.hooks.apply("UserPromptSubmit", {"prompt": text_of(prompt)})
            if hook.blocked:
                reason = hook.reason or "the prompt was blocked"
                self._publish(EventType.ERROR, {"error": reason})
                self._publish(EventType.TURN_END, {"stop_reason": "error", "error": reason, "calls": 0, "cost": 0.0})
                return TurnResult(
                    session_id=self.session.id,
                    turn_count=self.session.turn_count,
                    cost=0.0,
                    stop_reason="error",
                    error=reason,
                )
            if isinstance(hook.updated_input, str):
                """The hook rewrote the prompt. What the user typed is kept aside."""
                prompt = with_text(prompt, hook.updated_input)
                original = text_of(user_input)
            if hook.additional_context:
                prompt = with_text(prompt, f"{text_of(prompt)}\n\n[hook] {hook.additional_context}")
        prompt = with_text(prompt, expand_mentions(text_of(prompt), self.session.cwd, self.policy))
        """The files the user mentions go into the message, with their content."""
        ephemeral = REVIEW_NOTE if self.purpose == "review" else ""
        """The diff of a review is read once. It does not have to stay in the context."""
        self.context.append({"role": "user", "content": prompt}, original=original, ephemeral=ephemeral)
        turn_messages.append({"role": "user", "content": prompt})
        self.session.turn_count += 1
        self._set_state(SessionState.THINKING)

        stop_reason = "end_turn"
        error = ""
        cost = 0.0
        n_calls = 0
        stop_blocks = 0
        verify_rounds = 0
        schema_attempts = 0
        output = None
        base = self.session.total_cost
        before = (self.model.total_cost, self.model.total_tokens)
        while True:
            # The tools of the last round may have spent money too.
            before = self._bill(before)
            if self.cancel is not None and self.cancel():
                stop_reason = "interrupted"
                break
            if self._ceilings_hold():
                if self.max_turns and n_calls >= self.max_turns:
                    stop_reason = "max_turns"
                    break
                if self.cost_limit and self.session.total_cost >= self.cost_limit:
                    stop_reason = "cost_exceeded"
                    break
                if self.token_limit and self.session.total_tokens >= self.token_limit:
                    stop_reason = "token_limit"
                    break
            self.context.maybe_compact()
            self._route()
            try:
                response, error = self._query()
            except Interrupted:
                """The user stopped the turn while the model was answering."""
                stop_reason = "interrupted"
                break
            before = self._bill(before)
            if response is None:
                self._publish(EventType.ERROR, {"error": error})
                stop_reason = "error"
                break
            n_calls += 1
            response.setdefault("extra", {}).update(
                {
                    "purpose": self.purpose,
                    "model": getattr(self.model.backend, "model_name", ""),
                    "priced": self.model.priced,
                }
            )
            self._warn_unpriced(response)
            self.context.append(response)
            turn_messages.append(response)
            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                if stop_blocks < 3 and self._stop_blocked(response):
                    stop_blocks += 1
                    continue
                failure, exhausted = self._verify(verify_rounds)
                if failure:
                    """The work does not pass the check: the agent gets to try again."""
                    verify_rounds += 1
                    self.context.append({"role": "user", "content": failure})
                    turn_messages.append({"role": "user", "content": failure})
                    if exhausted:
                        stop_reason = "verify_failed"
                        error = failure
                        break
                    continue
                if self.output_schema:
                    """The answer has to fit the schema. When it does not, the model gets to try again."""
                    problems, value = self._check_schema(response)
                    if problems:
                        schema_attempts += 1
                        message = "[schema] The answer does not fit the schema.\n" + "\n".join(
                            f"- {problem}" for problem in problems
                        )
                        self.context.append({"role": "user", "content": message})
                        turn_messages.append({"role": "user", "content": message})
                        if schema_attempts >= MAX_SCHEMA_ATTEMPTS:
                            stop_reason = "schema_invalid"
                            error = "; ".join(problems)
                            break
                        continue
                    output = value
                break
            self._set_state(SessionState.EXECUTING)
            actions = self.executor.plan(tool_calls)
            self._publish(EventType.TOOL_CALL, {"actions": actions})
            observations = self.executor.execute(actions)
            self.context.extend(observations)
            turn_messages.extend(observations)
            self._set_state(SessionState.THINKING)

        self.context.forget_ephemeral()
        """The diff of a review is gone from the context. The rest of the session is not."""
        # What the turn cost: everything the agent spent, the sub agents and the summaries included.
        cost = self.session.total_cost - base
        self._publish(
            EventType.TURN_END,
            {"stop_reason": stop_reason, "error": error, "calls": n_calls, "cost": cost},
        )
        self._set_state(SessionState.ERROR if stop_reason == "error" else SessionState.DONE, stop_reason=stop_reason)
        self._session_end()
        self._export_trace()
        return TurnResult(
            session_id=self.session.id,
            turn_count=self.session.turn_count,
            cost=cost,
            stop_reason=stop_reason,
            messages=turn_messages,
            error=error,
            output=output,
        )

    def _check_schema(self, response: dict) -> tuple[list[str], Any]:
        """The ways the answer does not fit the schema, and the answer when it does."""
        value, reason = schema.parse(text_of(response.get("content")))
        if reason:
            return [reason], None
        errors = schema.validate(value, self.output_schema)
        return errors, None if errors else value

    def _verify(self, rounds: int) -> tuple[str, bool]:
        """Run the commands that check the work.

        Returns the message for the agent and whether the rounds are used up.
        The message is empty when the work passes, or when there is nothing to
        check.
        """
        if not self.verify or not self.verify.commands:
            return "", False
        failures = []
        for command in self.verify.commands:
            result = self._run_verify_command(command)
            if result["returncode"] != 0:
                failures.append(result)
        self._publish(
            EventType.VERIFY,
            {
                "commands": list(self.verify.commands),
                "failed": [failure["command"] for failure in failures],
                "round": rounds + 1,
            },
        )
        if not failures:
            return "", False
        message = "\n\n".join(
            [
                "[verify] These commands did not pass. Fix the problem and try again.",
                *[
                    f"$ {failure['command']}\n{failure['output']}\n[exit code {failure['returncode']}]"
                    for failure in failures
                ],
            ]
        )
        return message, rounds + 1 >= self.verify.max_rounds

    def _run_verify_command(self, command: str) -> dict:
        """Run one check in the environment of the session."""
        from coderagent.tools.builtin.shell import CodingEnvironment

        environment = self.sandbox or CodingEnvironment(cwd=str(self.session.cwd))
        cwd = str(self.session.cwd) if isinstance(environment, LocalEnvironment) else ""
        result = environment.execute({"command": command}, cwd=cwd, timeout=self.verify.timeout)
        output = str(result.get("output", ""))
        if result.get("exception_info"):
            output = f"{output}\n{result['exception_info']}".strip()
        return {
            "command": command,
            "output": trim_text(output, VERIFY_OUTPUT_TOKENS)[0],
            "returncode": int(result.get("returncode", 0)),
        }

    def _bill(self, before: tuple[float, int]) -> tuple[float, int]:
        """Put what the gateway spent on the bill of this session.

        The gateway is shared by all the sessions of the process, the bill is not: a
        session pays for its own calls only.
        """
        self.session.total_cost += self.model.total_cost - before[0]
        self.session.total_tokens += self.model.total_tokens - before[1]
        return (self.model.total_cost, self.model.total_tokens)

    def _ceilings_hold(self) -> bool:
        """Whether the ceilings of the session apply.

        Bypass means the session runs until the work is done: the money, the tokens
        and the number of the calls are not what stops it. The user stops it. A
        harness that measures asks for the ceilings anyway.
        """
        return self.enforce_ceilings or self.policy.mode != PermissionMode.BYPASS

    def _warn_unpriced(self, response: dict) -> None:
        """A model without a price spends no money, so a cost limit cannot be enforced."""
        if not self.cost_limit or self._warned_unpriced:
            return
        extra = response.get("extra") or {}
        if extra.get("tokens_in") and not extra.get("cost"):
            logger.warning(
                "The model %s has no price, so the cost limit cannot be enforced. Use agent.token_limit instead.",
                getattr(self.model.backend, "model_name", ""),
            )
            self._warned_unpriced = True

    def _route(self) -> None:
        """Pick the model of this turn. A change is announced in the event stream."""
        if self.router is None:
            return
        name = self.router.resolve(self.purpose, self._routing_context())
        if not name:
            return
        backend = self.router.backend_for(name)
        current = getattr(self.model.backend, "model_name", "")
        if backend.model_name == current:
            """The same model behind another name. There is nothing to change."""
            return
        self.model.backend = backend
        self._publish(
            EventType.STATE_CHANGE,
            {
                "state": self.session.state.value,
                "model": name,
                "previous": current,
                "reason": self._route_reason(),
            },
        )

    def _routing_context(self) -> dict:
        """What the router knows about the session."""
        return {
            "tokens": self.context.estimated_tokens(self.tools),
            "turns": self.session.turn_count,
            "calls": self.model.n_calls,
            "cost": self.session.total_cost,
            "budget": self.cost_limit,
            "tokens_used": self.session.total_tokens,
            "token_budget": self.token_limit,
        }

    def _route_reason(self) -> str:
        """Why the model changed, in one line."""
        return self.router.explain(self._routing_context())

    def _stop_blocked(self, response: dict) -> bool:
        """Ask the Stop hook whether the agent may stop. A blocked stop means: keep going."""
        if not self.hooks:
            return False
        hook = self.hooks.apply("Stop", {"last_message": response.get("content", "")})
        if not hook.blocked:
            return False
        self.context.append({"role": "user", "content": f"[hook] {hook.reason}"})
        return True

    def _session_start(self) -> None:
        if self.hooks:
            self.hooks.apply("SessionStart", {"session_id": self.session.id, "cwd": str(self.session.cwd)})

    def _session_end(self) -> None:
        if self.hooks:
            self.hooks.apply(
                "SessionEnd",
                {"session_id": self.session.id, "turns": self.session.turn_count, "cost": self.session.total_cost},
            )

    def _export_trace(self) -> None:
        """Send the spans of this turn to the backend, when there is one.

        What the backend has seen is not sent again. A backend that is down is
        a warning: the trace stays in the event log either way.
        """
        if self.exporter is None:
            return
        events = self.store.events(self.session.id)
        fresh = events[self._exported :]
        if not fresh:
            return
        payload = build_trace(fresh, self.session)
        if not payload["resourceSpans"][0]["scopeSpans"][0]["spans"]:
            self._exported = len(events)
            return
        if self.exporter.export(payload):
            self._exported = len(events)

    def _query(self) -> tuple[dict | None, str]:
        """Ask the model. When the provider says the context is too big, compact and try once more."""
        try:
            return self._collect(), ""
        except Interrupted:
            """The turn was stopped: this is not an error of the provider."""
            raise
        except Exception as e:
            if not is_context_overflow(e):
                return None, f"{type(e).__name__}: {e}"
            if not self.context.force_compact():
                return None, f"{type(e).__name__}: {e} (nothing left to compact)"
            try:
                return self._collect(), ""
            except Interrupted:
                raise
            except Exception as retry_error:
                return None, f"{type(retry_error).__name__}: {retry_error}"

    def _collect(self) -> dict:
        """Read the answer as it arrives and fold it into one message."""
        events = self.model.query_stream(self.context.build_messages(tools=self.tools), tools=self.tools)
        return message_from_events(self._announce(events))

    def _announce(self, events) -> Iterator[ModelEvent]:
        """Publish the pieces of the answer, so the UI can show them while they arrive."""
        for event in events:
            if self.cancel is not None and self.cancel():
                """The answer is cut short: the user does not wait for the rest of it."""
                raise Interrupted()
            if event.type == "text":
                self._notify(EventType.TEXT_DELTA, {"content": event.content})
            elif event.type == "reasoning":
                self._notify(EventType.REASONING, {"content": event.content})
            yield event

    def _notify(self, event_type: EventType, payload: dict) -> None:
        """Publish to the UI only. The event log keeps the whole messages."""
        self.bus.publish(Event(type=event_type, session_id=self.session.id, timestamp=time.time(), payload=payload))

    def _publish(self, event_type: EventType, payload: dict) -> None:
        event = Event(type=event_type, session_id=self.session.id, timestamp=time.time(), payload=payload)
        self.bus.publish(event)
        self.store.append(self.session.id, event)

    def _set_state(self, state: SessionState, **extra) -> None:
        self.session.state = state
        self._publish(EventType.STATE_CHANGE, {"state": state.value, **extra})
