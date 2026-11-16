"""The review of the changes: the diff goes into the prompt of a turn."""

import subprocess
from pathlib import Path

from coderagent.config.schema import Config
from coderagent.core.events import EventBus
from coderagent.core.loop import AgentLoop
from coderagent.core.session import SessionStore
from coderagent.models.gateway import ModelGateway
from coderagent.models.router import ModelRouter
from coderagent.testing.factory import build_executor
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.tools.permissions import PermissionMode, PermissionPolicy
from coderagent.ui.commands import CommandContext, run
from coderagent.ui.commands.review import MAX_DIFF, prompt


def _context(tmp_path, cwd: Path) -> tuple[CommandContext, list[str], list[str], list[str]]:
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    executor = build_executor(cwd)
    loop = AgentLoop(
        ModelGateway(ScriptedModel([{"role": "assistant", "content": "ok"}])),
        executor,
        session,
        store,
        EventBus(),
        tools=executor.registry.schemas(),
        router=ModelRouter(Config().model),
    )
    output: list[str] = []
    submitted: list[str] = []
    purposes: list[str] = []

    def submit(text, purpose: str = "") -> None:
        submitted.append(text)
        purposes.append(purpose)

    context = CommandContext(
        loop=loop,
        session=session,
        store=store,
        bus=loop.bus,
        cwd=cwd,
        config=Config(),
        policy=PermissionPolicy(PermissionMode.DEFAULT, [], cwd=cwd),
        output=output.append,
        submit=submit,
    )
    return context, output, submitted, purposes


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path) -> Path:
    """A repository with one commit, in a directory of its own."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.py").write_text("print('a')\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-m", "first")
    return repo


def test_the_diff_of_the_working_tree_goes_into_the_prompt(tmp_path):
    repo = _repo(tmp_path)
    (repo / "a.py").write_text("print('b')\n", encoding="utf-8")
    context, output, submitted, purposes = _context(tmp_path, repo)

    run(context, "/review")

    assert len(submitted) == 1
    assert "-print('a')" in submitted[0]
    assert "+print('b')" in submitted[0]


def test_a_range_is_reviewed_instead_of_the_working_tree(tmp_path):
    repo = _repo(tmp_path)
    (repo / "a.py").write_text("print('b')\n", encoding="utf-8")
    _git(repo, "commit", "-am", "second")
    (repo / "a.py").write_text("print('c')\n", encoding="utf-8")
    context, output, submitted, purposes = _context(tmp_path, repo)

    run(context, "/review HEAD~1..HEAD")

    assert "-print('a')" in submitted[0]
    assert "+print('b')" in submitted[0]
    assert "+print('c')" not in submitted[0]


def test_the_new_files_are_named_even_when_they_are_not_in_the_diff(tmp_path):
    repo = _repo(tmp_path)
    (repo / "b.py").write_text("print('b')\n", encoding="utf-8")
    context, output, submitted, purposes = _context(tmp_path, repo)

    run(context, "/review")

    assert "b.py" in submitted[0]


def test_the_review_asks_for_the_review_purpose(tmp_path):
    repo = _repo(tmp_path)
    (repo / "a.py").write_text("print('b')\n", encoding="utf-8")
    context, output, submitted, purposes = _context(tmp_path, repo)

    run(context, "/review")

    assert purposes == ["review"]


def test_nothing_to_review_says_so(tmp_path):
    repo = _repo(tmp_path)
    context, output, submitted, purposes = _context(tmp_path, repo)

    run(context, "/review")

    assert "No changes to review." in "\n".join(output)
    assert submitted == []


def test_a_directory_that_is_not_a_repository_says_so(tmp_path):
    context, output, submitted, purposes = _context(tmp_path, tmp_path)

    run(context, "/review")

    assert "Not a git repository" in "\n".join(output)
    assert submitted == []


def test_a_range_that_git_does_not_know_says_so(tmp_path):
    repo = _repo(tmp_path)
    context, output, submitted, purposes = _context(tmp_path, repo)

    run(context, "/review nope..nope")

    assert "Git does not know" in "\n".join(output)
    assert submitted == []


def test_an_interface_that_cannot_run_a_turn_says_so(tmp_path):
    repo = _repo(tmp_path)
    (repo / "a.py").write_text("print('b')\n", encoding="utf-8")
    context, output, submitted, purposes = _context(tmp_path, repo)
    context.submit = None

    run(context, "/review")

    assert "cannot run a turn" in "\n".join(output)


def test_the_prompt_asks_for_findings_and_not_for_changes():
    text = prompt("diff --git a/a.py b/a.py", [], "")
    assert "Do not change any file" in text
    assert "diff --git a/a.py b/a.py" in text


def test_a_diff_that_is_too_long_is_cut():
    text = prompt("x" * (MAX_DIFF + 100), [], "")
    assert "the diff is cut here" in text
    assert len(text) < MAX_DIFF + 1000
