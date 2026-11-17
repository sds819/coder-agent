"""Session state and its persistence. Events are the source of truth, the session is derived."""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from coderagent.core.events import Event, EventType
from coderagent.core.telemetry import collect
from coderagent.paths import config_home

logger = logging.getLogger("coderagent.core.session")

PERSISTENCES = ("save-all", "save-none")
"""How the history of the sessions is kept: on the disk, or nowhere."""


class SessionState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    ERROR = "error"


@dataclass
class Session:
    id: str
    cwd: Path
    created_at: float
    updated_at: float
    state: SessionState = SessionState.IDLE
    model_name: str = ""
    permission_mode: str = "default"
    turn_count: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    """The tokens of the session, in and out. The budget of a model that has no price."""
    name: str = ""
    """The name the user gave to the session."""
    archived: bool = False
    """Whether the session is put away. An archived session is not in the list."""
    metadata: dict = field(default_factory=dict)


def default_root() -> Path:
    """Directory holding all session files. Overridable via `MSWEA_CODER_HOME`."""
    return config_home() / "sessions"


class SessionStore:
    """Append-only JSONL event log. Replaying the log rebuilds the session."""

    def __init__(self, root: Path | None = None, *, persist: bool = True, max_bytes: int = 0) -> None:
        self.root = Path(root) if root else default_root()
        self.persist = persist
        """Whether the history is written to the disk. When it is not, the session lives in memory."""
        self.max_bytes = max_bytes
        """The bytes the history of all the sessions may take. 0 means no limit."""
        self._size = 0
        """The bytes the history takes, as far as it is known."""
        self._measured = False
        """Whether the size of the history has been measured on the disk."""

    def create(self, cwd: Path) -> Session:
        session = Session(
            id=f"{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
            cwd=Path(cwd),
            created_at=time.time(),
            updated_at=time.time(),
        )
        if not self.persist:
            """The history is not kept, so there is nothing to write."""
            return session
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_meta(session)
        self.append(
            session.id,
            Event(
                type=EventType.STATE_CHANGE,
                session_id=session.id,
                timestamp=session.created_at,
                payload={"state": session.state.value, "cwd": str(session.cwd), "created_at": session.created_at},
            ),
        )
        return session

    def path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def meta_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.meta.json"

    def append(self, session_id: str, event: Event) -> None:
        if not self.persist:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with self.path(session_id).open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self._size += len(line.encode("utf-8"))
        if self.max_bytes:
            if not self._measured:
                self._size = self._total_size()
                self._measured = True
            if self._size > self.max_bytes:
                self._prune(session_id)

    def events(self, session_id: str) -> list[Event]:
        path = self.path(session_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = Event.from_dict(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("A line of the session log is broken, it is skipped: %s", line[:120])
                continue
            if event is not None:
                events.append(event)
        return events

    def rebuild(self, session_id: str) -> Session:
        """Replay the event log to get the current session state."""
        session = Session(id=session_id, cwd=Path("."), created_at=0.0, updated_at=0.0)
        events = self.events(session_id)
        for event in events:
            payload = event.payload
            if event.type == EventType.STATE_CHANGE:
                session.state = SessionState(payload.get("state", session.state.value))
                if "cwd" in payload:
                    session.cwd = Path(payload["cwd"])
                if "created_at" in payload:
                    session.created_at = payload["created_at"]
                if "model_name" in payload:
                    session.model_name = payload["model_name"]
                if "permission_mode" in payload:
                    session.permission_mode = payload["permission_mode"]
                if "name" in payload:
                    session.name = payload["name"]
                if "archived" in payload:
                    session.archived = bool(payload["archived"])
                if "parent" in payload:
                    session.metadata["parent"] = payload["parent"]
            elif event.type == EventType.USER_MESSAGE:
                session.turn_count += 1
            elif event.type == EventType.TOOL_RESULT and payload.get("todos"):
                session.metadata["todos"] = payload["todos"]
            elif event.type == EventType.TURN_END:
                session.metadata["stop_reason"] = payload.get("stop_reason", "")
            session.updated_at = event.timestamp
        # The cost of the session is the cost of every call in the log, the sub agents included.
        metrics = collect(events)
        session.total_cost = metrics.total_cost
        session.total_tokens = metrics.total_tokens_in + metrics.total_tokens_out
        return session

    def list(self, cwd: Path | None = None, archived: bool | None = None) -> list[Session]:
        """All sessions, newest first. Optionally restricted to a working directory.

        `archived` says which ones are wanted: the ones that are put away, the ones
        that are not, or all of them.
        """
        if not self.root.exists():
            return []
        sessions = []
        for meta_path in self.root.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("The meta file of a session is broken, it is skipped: %s", meta_path)
                continue
            if cwd is not None and Path(meta.get("cwd", "")) != Path(cwd):
                continue
            session = self.rebuild(meta["id"])
            if archived is not None and session.archived != archived:
                continue
            sessions.append(session)
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)

    def fork(self, session_id: str) -> Session:
        """Copy a session into a new one. The original stays untouched."""
        source = self.rebuild(session_id)
        forked = Session(
            id=f"{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
            cwd=source.cwd,
            created_at=time.time(),
            updated_at=time.time(),
            model_name=source.model_name,
            permission_mode=source.permission_mode,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_meta(forked)
        for event in self.events(session_id):
            self.append(
                forked.id,
                Event(
                    type=event.type,
                    session_id=forked.id,
                    timestamp=event.timestamp,
                    payload=event.payload,
                ),
            )
        self.append(
            forked.id,
            Event(
                type=EventType.STATE_CHANGE,
                session_id=forked.id,
                timestamp=forked.created_at,
                payload={
                    "state": source.state.value,
                    "cwd": str(forked.cwd),
                    "created_at": forked.created_at,
                },
            ),
        )
        return self.rebuild(forked.id)

    def side(self, session_id: str) -> Session:
        """A copy of a session, for a conversation that goes aside.

        The copy knows its parent, so the session it came from is not lost.
        The original is not touched.
        """
        side = self.fork(session_id)
        self.append(
            side.id,
            Event(
                type=EventType.STATE_CHANGE,
                session_id=side.id,
                timestamp=time.time(),
                payload={"parent": session_id},
            ),
        )
        return self.rebuild(side.id)

    def _write_meta(self, session: Session) -> None:
        meta = {
            "id": session.id,
            "cwd": str(session.cwd),
            "created_at": session.created_at,
            "model_name": session.model_name,
        }
        path = self.meta_path(session.id)
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    # -- the life of a session ---------------------------------------------

    def rename(self, session_id: str, name: str) -> bool:
        """Give a session a name. Returns whether there is such a session."""
        return self._state_event(session_id, {"name": name})

    def archive(self, session_id: str, archived: bool = True) -> bool:
        """Put a session away, or take it out again. Returns whether there is such a session."""
        return self._state_event(session_id, {"archived": archived})

    def delete(self, session_id: str) -> bool:
        """Remove a session and everything in it. Returns whether there was such a session."""
        path = self.path(session_id)
        if not path.exists():
            return False
        path.unlink()
        meta = self.meta_path(session_id)
        if meta.exists():
            meta.unlink()
        return True

    def _state_event(self, session_id: str, payload: dict) -> bool:
        """Write a state of the session into its log."""
        if not self.path(session_id).exists():
            return False
        self.append(
            session_id,
            Event(
                type=EventType.STATE_CHANGE,
                session_id=session_id,
                timestamp=time.time(),
                payload=payload,
            ),
        )
        return True

    def _total_size(self) -> int:
        """The bytes the history of all the sessions takes."""
        return sum(path.stat().st_size for path in self.root.glob("*.jsonl"))

    def _prune(self, keep: str) -> None:
        """Delete the oldest sessions until the history fits into the limit."""
        logs = sorted(self.root.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in logs)
        for path in logs:
            if total <= self.max_bytes:
                break
            if path.stem == keep:
                continue
            """The session that is running is never deleted."""
            total -= path.stat().st_size
            self.delete(path.stem)
        self._size = total
