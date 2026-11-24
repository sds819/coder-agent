import json

from coderagent.core.events import Event, EventType
from coderagent.core.session import SessionStore


def _message(session_id: str, text: str) -> Event:
    return Event(type=EventType.USER_MESSAGE, session_id=session_id, timestamp=1.0, payload={"content": text})


def test_a_broken_line_does_not_lose_the_session(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    store.append(session.id, _message(session.id, "first"))
    with store.path(session.id).open("a", encoding="utf-8") as f:
        f.write('{"type": "user_message", "payl\n')
    store.append(session.id, _message(session.id, "second"))

    events = store.events(session.id)
    assert [event.payload.get("content") for event in events if event.type == EventType.USER_MESSAGE] == [
        "first",
        "second",
    ]
    assert store.rebuild(session.id).turn_count == 2


def test_a_broken_meta_file_does_not_lose_the_other_sessions(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    (tmp_path / "sessions" / "broken.meta.json").write_text("{not json", encoding="utf-8")

    assert [item.id for item in store.list()] == [session.id]


def test_the_meta_file_is_written_at_once(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)

    assert json.loads(store.meta_path(session.id).read_text(encoding="utf-8"))["id"] == session.id
    assert [path.name for path in (tmp_path / "sessions").iterdir() if path.name.endswith(".tmp")] == []


def test_the_events_are_on_the_disk_right_away(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    store.append(session.id, _message(session.id, "hello"))

    assert store.events(session.id)[-1].payload["content"] == "hello"


def test_a_session_can_be_named(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)

    assert store.rename(session.id, "the bug of monday")
    assert store.rebuild(session.id).name == "the bug of monday"


def test_the_summary_of_a_session_is_its_first_question(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    store.append(session.id, _message(session.id, "fix the failing test"))
    store.append(session.id, _message(session.id, "and then the other one"))

    assert store.rebuild(session.id).summary == "fix the failing test"


def test_a_long_question_is_cut_short(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    store.append(session.id, _message(session.id, "a line\nand another one " + "x" * 100))

    summary = store.rebuild(session.id).summary
    assert summary.startswith("a line and another one xxx")
    assert summary.endswith("…")
    assert len(summary) == 41


def test_a_session_that_is_not_there_cannot_be_named(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    assert store.rename("nope", "the bug of monday") is False


def test_a_session_can_be_put_away_and_taken_out(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)

    assert store.archive(session.id)
    assert store.rebuild(session.id).archived is True
    assert store.list(archived=False) == []
    assert [item.id for item in store.list(archived=True)] == [session.id]

    assert store.archive(session.id, False)
    assert store.rebuild(session.id).archived is False
    assert [item.id for item in store.list()] == [session.id]


def test_a_session_can_be_deleted(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    store.append(session.id, _message(session.id, "hello"))

    assert store.delete(session.id)
    assert store.events(session.id) == []
    assert store.list() == []
    assert not store.meta_path(session.id).exists()


def test_a_session_that_is_not_there_cannot_be_deleted(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    assert store.delete("nope") is False


def test_the_history_is_not_written_when_it_is_not_saved(tmp_path):
    store = SessionStore(tmp_path / "sessions", persist=False)
    session = store.create(tmp_path)
    store.append(session.id, _message(session.id, "hello"))

    assert store.events(session.id) == []
    assert list((tmp_path / "sessions").glob("*")) == []


def test_the_oldest_sessions_are_deleted_when_the_history_is_too_big(tmp_path):
    store = SessionStore(tmp_path / "sessions", max_bytes=400)
    old = store.create(tmp_path)
    store.append(old.id, _message(old.id, "old"))
    new = store.create(tmp_path)
    store.append(new.id, _message(new.id, "new" * 200))

    assert store.events(old.id) == []
    assert store.events(new.id)
