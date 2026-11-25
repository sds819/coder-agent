"""The terminal interface: the widgets and the app."""

import asyncio
import subprocess
import threading
import time

import pytest

from coderagent.config.schema import Config
from coderagent.core.events import Event, EventBus, EventType
from coderagent.core.session import SessionStore
from coderagent.run import build_loop
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.tools.permissions import ApprovalDecision
from coderagent.ui.widgets.diff_view import make_diff, prospective_diff
from coderagent.ui.widgets.session_picker import SessionPicker
from coderagent.ui.widgets.tool_card import summarize

pytest.importorskip("textual")

from textual.widgets import Input  # noqa: E402

from coderagent.ui.tui import CoderApp, TUIAprover  # noqa: E402
from coderagent.ui.widgets import FileTree, MarkdownMessage, MessageBlock, ToolCard, WorkingDots  # noqa: E402


def _app(tmp_path, responses=None, mode="default", markdown=True, include_dirs=None):
    config = Config()
    config.permissions.mode = mode
    config.permissions.include_dirs = include_dirs or []
    config.ui.markdown = markdown
    config.model.capabilities = {"scripted": {"image": True}}
    """The model of the tests looks at pictures."""
    bus = EventBus()
    approver = TUIAprover(bus)
    model = ScriptedModel(responses or [{"role": "assistant", "content": "hello", "extra": {"cost": 0.0}}])
    loop = build_loop(config, tmp_path, bus=bus, approver=approver, model=model)
    return CoderApp(config, tmp_path, bus=bus, approver=approver, store=loop.store, session=loop.session, loop=loop)


async def _wait_for(predicate, timeout=10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


def _assistant_blocks(app) -> list:
    """The answer of the agent: the plain block while it arrives, the Markdown when it is complete."""
    rendered = list(app.query(MarkdownMessage))
    if rendered:
        return rendered
    return [block for block in app.query(MessageBlock) if block.role == "assistant"]


def _command_blocks(app) -> list:
    return [block for block in app.query(MessageBlock) if block.role == "command"]


def test_the_diff_of_two_texts():
    diff = make_diff("one\ntwo\n", "one\nthree\n", "a.py")
    assert "-two" in diff
    assert "+three" in diff
    assert "a/a.py" in diff


def test_the_diff_a_tool_is_about_to_make(tmp_path):
    (tmp_path / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    diff = prospective_diff("edit", {"path": "a.py", "old_string": "two", "new_string": "three"}, tmp_path)
    assert "-two" in diff
    assert "+three" in diff


def test_the_diff_of_a_new_file(tmp_path):
    diff = prospective_diff("write", {"path": "b.py", "content": "hello\n"}, tmp_path)
    assert "+hello" in diff


def test_the_summary_of_the_arguments():
    assert summarize({"path": "a.py"}) == "path=a.py"
    assert summarize({"command": "ls"}) == "command=ls"
    assert summarize({}) == ""


def test_the_dots_say_that_the_agent_is_working(tmp_path):
    """The agent is thinking: the dots show, and they go when it says something."""
    app = _app(tmp_path)
    seen = []

    async def go():
        async with app.run_test() as pilot:
            app.bus.publish(
                Event(type=EventType.STATE_CHANGE, session_id="", timestamp=0.0, payload={"state": "thinking"})
            )
            await pilot.pause()
            seen.append(len(list(app.query(WorkingDots))))
            app.bus.publish(Event(type=EventType.STATE_CHANGE, session_id="", timestamp=0.0, payload={"state": "done"}))
            await pilot.pause()
            seen.append(len(list(app.query(WorkingDots))))

    asyncio.run(go())
    assert seen == [1, 0]


def test_no_dots_are_left_after_a_turn(tmp_path):
    """The dots are the sign that the agent works: a turn that is over has none."""
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))
            assert await _wait_for(lambda: not list(app.query(WorkingDots)))

    asyncio.run(go())


def test_the_dots_move(tmp_path):
    """The dots are an animation, not a sign that stands still."""
    app = _app(tmp_path)
    frames = []

    async def go():
        async with app.run_test() as pilot:
            app.bus.publish(
                Event(type=EventType.STATE_CHANGE, session_id="", timestamp=0.0, payload={"state": "thinking"})
            )
            await pilot.pause()
            for _ in range(6):
                frames.append(app.query_one(WorkingDots).content)
                await asyncio.sleep(0.2)

    asyncio.run(go())
    assert len(set(frames)) > 1


def test_the_app_shows_the_answer(tmp_path):
    app = _app(tmp_path)
    blocks = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))
            blocks.extend(_assistant_blocks(app))

    asyncio.run(go())
    assert blocks[0].content == "hello"


def test_the_answer_is_rendered_as_markdown(tmp_path):
    """The answer of the agent is Markdown: the code blocks and the lists look right."""
    answer = "# Title\n\n- one\n- two\n"
    app = _app(tmp_path, responses=[{"role": "assistant", "content": answer, "extra": {"cost": 0.0}}])
    blocks = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))
            blocks.extend(_assistant_blocks(app))

    asyncio.run(go())
    assert isinstance(blocks[0], MarkdownMessage)
    assert blocks[0].content == answer


def test_the_markdown_can_be_turned_off(tmp_path):
    """The user who wants plain text gets plain text."""
    app = _app(tmp_path, markdown=False)
    blocks = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))
            blocks.extend(_assistant_blocks(app))

    asyncio.run(go())
    assert not list(app.query(MarkdownMessage))
    assert blocks[0].content == "hello"


def test_the_image_reaches_the_model(tmp_path):
    """The `/image` command sends the picture with the text that goes with it."""
    import base64

    (tmp_path / "shot.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
    )
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"/image shot.png what is this")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))

    asyncio.run(go())
    content = app.loop.model.backend.calls[0][-1]["content"]
    assert content[0] == {"type": "text", "text": "what is this"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_the_status_bar_shows_the_session(tmp_path):
    app = _app(tmp_path)
    bar = []

    async def go():
        async with app.run_test():
            await asyncio.sleep(0.1)
            bar.append(app.query_one("StatusBar"))

    asyncio.run(go())
    assert bar[0].model == app.loop.model.backend.model_name
    assert bar[0].mode == "default"


def test_the_app_loads_litellm_while_it_waits_for_the_user(tmp_path):
    """The screen is up and litellm loads behind it: the first prompt does not wait."""
    from coderagent.models import litellm_module

    litellm_module.cache_clear()
    app = _app(tmp_path)

    async def go():
        async with app.run_test():
            assert await _wait_for(lambda: litellm_module.cache_info().currsize == 1, timeout=30)

    asyncio.run(go())


def test_the_status_bar_shows_the_sandbox_when_it_is_not_local():
    from coderagent.ui.widgets import StatusBar

    bar = StatusBar()
    bar.update_status(model="m", sandbox="swerex_docker", mode="default")
    assert "swerex_docker" in str(bar.render())
    bar.update_status(sandbox="local")
    assert "local" not in str(bar.render())


def test_the_status_bar_says_that_the_money_of_a_model_without_a_price_is_unknown():
    from coderagent.ui.widgets import StatusBar

    bar = StatusBar()
    bar.update_status(model="m", cost=0.0, priced=False)
    assert "$?" in str(bar.render())
    bar.update_status(priced=True)
    assert "$0.0000" in str(bar.render())


def test_a_command_is_answered(tmp_path):
    app = _app(tmp_path)
    blocks = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"/help")
            await pilot.press("enter")
            assert await _wait_for(lambda: _command_blocks(app))
            blocks.extend(_command_blocks(app))

    asyncio.run(go())
    assert "compact" in blocks[0].content


def test_a_command_does_not_touch_the_answer_of_the_agent(tmp_path):
    """The answer of a command is a message of its own: the answer of the agent stays."""
    app = _app(tmp_path)
    answers = []
    commands = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))
            await pilot.press(*"/help")
            await pilot.press("enter")
            assert await _wait_for(lambda: _command_blocks(app))
            answers.extend(_assistant_blocks(app))
            commands.extend(_command_blocks(app))

    asyncio.run(go())
    assert answers[0].content == "hello"
    assert "compact" in commands[0].content


def test_the_command_that_was_typed_is_shown(tmp_path):
    app = _app(tmp_path)
    typed = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"/help")
            await pilot.press("enter")
            assert await _wait_for(lambda: _command_blocks(app))
            typed.extend(block.content for block in app.query(MessageBlock) if block.role == "user")

    asyncio.run(go())
    assert typed == ["/help"]


def test_the_card_of_a_tool_call_is_shown(tmp_path):
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "bash", "arguments": '{"command": "sh -c \'echo hi\'"}'},
    }
    app = _app(
        tmp_path,
        responses=[
            {"role": "assistant", "content": "", "tool_calls": [call], "extra": {"cost": 0.0}},
            {"role": "assistant", "content": "done", "extra": {"cost": 0.0}},
        ],
        mode="bypass",
    )
    cards = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"run it")
            await pilot.press("enter")
            assert await _wait_for(lambda: app.query(ToolCard))
            assert await _wait_for(lambda: app.query_one(ToolCard).content)
            cards.extend(app.query(ToolCard))

    asyncio.run(go())
    assert cards[0].tool == "bash"
    assert "hi" in cards[0].content


def test_the_brackets_of_the_model_do_not_break_the_message():
    """The text of the model is not markup: a bracket in it must not break the widget."""
    from textual.content import Content

    from coderagent.ui.widgets import MessageBlock

    text = "[Function(name='read'), id='call_1', type='function')] and [1]"
    block = MessageBlock("assistant", text)
    assert block.content == text
    assert text in str(Content.from_markup(block.render()))


def test_the_brackets_of_the_model_do_not_break_the_card():
    """The output of a tool is not markup either."""
    from textual.content import Content

    from coderagent.ui.widgets import ToolCard

    text = "[Function(name='read'), id='call_1', type='function')]"
    card = ToolCard("read", {"path": text})
    card.finish(text, False, "")
    assert card.content == text
    assert text in str(Content.from_markup(card.render()))


def test_a_message_with_brackets_is_shown(tmp_path):
    from textual.widgets import Markdown

    answer = "[Function(name='read'), id='call_1', type='function')]"
    app = _app(tmp_path, responses=[{"role": "assistant", "content": answer, "extra": {"cost": 0.0}}])
    blocks = []
    sources = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))
            assert await _wait_for(lambda: list(app.query(Markdown)))
            blocks.extend(_assistant_blocks(app))
            sources.append(app.query_one(Markdown).source)

    asyncio.run(go())
    assert blocks[0].content == answer
    assert answer in sources[0]


def test_the_approval_is_asked_and_the_tool_runs(tmp_path):
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "bash", "arguments": '{"command": "sh -c \'echo hi\'"}'},
    }
    app = _app(
        tmp_path,
        responses=[
            {"role": "assistant", "content": "", "tool_calls": [call], "extra": {"cost": 0.0}},
            {"role": "assistant", "content": "done", "extra": {"cost": 0.0}},
        ],
        mode="default",
    )
    asked = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"write it")
            await pilot.press("enter")
            assert await _wait_for(lambda: app.pending_approval is not None)
            asked.append(app.pending_approval.tool)
            await pilot.press("y")
            assert await _wait_for(lambda: app.pending_approval is None)

    asyncio.run(go())
    assert asked == ["bash"]


def test_the_answers_are_picked_with_the_arrow_keys(tmp_path):
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "bash", "arguments": '{"command": "sh -c \'echo hi\'"}'},
    }
    app = _app(
        tmp_path,
        responses=[
            {"role": "assistant", "content": "", "tool_calls": [call], "extra": {"cost": 0.0}},
            {"role": "assistant", "content": "done", "extra": {"cost": 0.0}},
        ],
        mode="default",
    )
    decisions = []
    answer = app.approver.answer

    def record(key, decision):
        decisions.append(decision)
        answer(key, decision)

    app.approver.answer = record

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"write it")
            await pilot.press("enter")
            assert await _wait_for(lambda: app.pending_approval is not None)
            prompt = app.pending_approval
            assert prompt.selected_key == "y"
            await pilot.press("right")
            assert prompt.selected_key == "n"
            await pilot.press("down")
            assert prompt.selected_key == "a"
            await pilot.press("up")
            assert prompt.selected_key == "n"
            await pilot.press("left")
            assert prompt.selected_key == "y"
            await pilot.press("right")
            await pilot.press("enter")
            assert await _wait_for(lambda: app.pending_approval is None)

    asyncio.run(go())
    assert decisions == [ApprovalDecision.DENY]


def test_the_selected_answer_is_red(tmp_path):
    from coderagent.ui.widgets import ApprovalPrompt

    prompt = ApprovalPrompt("bash", {"command": "ls"}, "")
    assert "\\[[red]*[/red]] [bold]y[/bold] allow" in prompt.options.markup()
    assert "\\[[gray]-[/gray]] [bold]n[/bold] deny" in prompt.options.markup()
    prompt.move(1)
    assert "\\[[red]*[/red]] [bold]n[/bold] deny" in prompt.options.markup()
    assert "\\[[red]*[/red]] [bold]y[/bold] allow" not in prompt.options.markup()


def test_the_answers_are_one_per_line_and_numbered(tmp_path):
    from coderagent.ui.widgets import ApprovalPrompt

    prompt = ApprovalPrompt("bash", {"command": "ls"}, "")
    lines = prompt.options.markup().split("\n")
    assert len(lines) == 4
    assert lines[0].startswith("[bold]1[/bold] ")
    assert "[bold]y[/bold] allow" in lines[0]
    assert lines[1].startswith("[gray]2[/gray] ")
    assert "[bold]n[/bold] deny" in lines[1]
    assert lines[2].startswith("[gray]3[/gray] ")
    assert "[bold]a[/bold] always allow" in lines[2]


def test_several_answers_can_be_picked(tmp_path):
    from coderagent.ui.widgets import Options

    options = Options((("y", "allow"), ("n", "deny"), ("a", "always allow")), multi=True)
    assert options.selected_keys == ["y"]
    options.toggle(2)
    options.toggle(2)
    assert options.selected_keys == ["y"]
    options.toggle(1)
    assert options.selected_keys == ["y", "n"]
    assert options.markup().count("\\[[red]*[/red]]") == 2
    options.move(1)
    assert options.selected_keys == ["y", "n"]
    assert options.markup().count("\\[[gray]-[/gray]]") == 1


def _repo(tmp_path):
    """A repository with one commit."""
    for args in (
        ["git", "init"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, check=True, capture_output=True)


def test_the_review_command_gives_the_diff_to_the_model(tmp_path):
    """The review is a turn of the session: the diff goes into the prompt."""
    _repo(tmp_path)
    (tmp_path / "a.py").write_text("print('b')\n", encoding="utf-8")
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"/review")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))

    asyncio.run(go())
    assert "+print('b')" in str(app.loop.model.backend.calls[0])


def test_the_exit_command_leaves_the_interface(tmp_path):
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"/exit")
            await pilot.press("enter")
            await pilot.pause()
            return app.is_running

    assert asyncio.run(go()) is False


def test_the_approver_waits_for_the_answer(tmp_path):
    bus = EventBus()
    approver = TUIAprover(bus)
    seen = []
    bus.subscribe(EventType.APPROVAL_REQUEST, lambda event: seen.append(event.payload))
    results = []

    thread = threading.Thread(target=lambda: results.append(approver.request("bash", {"command": "ls"}, "why")))
    thread.start()
    for _ in range(200):
        if seen:
            break
        time.sleep(0.01)
    assert seen[0]["tool"] == "bash"
    approver.answer(seen[0]["id"], ApprovalDecision.ALLOW)
    thread.join(timeout=5)
    assert results[0] is ApprovalDecision.ALLOW


def test_the_messages_that_were_sent_can_be_seen_again(tmp_path):
    """The up and down keys walk through the messages the user sent."""
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"first")
            await pilot.press("enter")
            await pilot.press(*"second")
            await pilot.press("enter")
            await pilot.press("up")
            assert app.query_one(Input).value == "second"
            await pilot.press("up")
            assert app.query_one(Input).value == "first"
            await pilot.press("down")
            assert app.query_one(Input).value == "second"
            await pilot.press("down")
            assert app.query_one(Input).value == ""

    asyncio.run(go())


def test_the_message_that_is_being_written_is_kept(tmp_path):
    """Walking back in the history and forward again gives the draft back."""
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"sent")
            await pilot.press("enter")
            await pilot.press(*"draft")
            await pilot.press("up")
            assert app.query_one(Input).value == "sent"
            await pilot.press("down")
            assert app.query_one(Input).value == "draft"

    asyncio.run(go())


def test_a_session_can_be_picked(tmp_path):
    """The panel of the sessions continues the one that is picked."""
    app = _app(tmp_path)
    commands = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press("ctrl+o")
            await pilot.pause()
            assert isinstance(app.screen, SessionPicker)
            await pilot.press("enter")
            await pilot.pause()
            commands.extend(_command_blocks(app))

    asyncio.run(go())
    assert commands[0].content == f"Resumed {app.loop.session.id}"


def test_the_picker_shows_the_first_question(tmp_path):
    """The panel of the sessions lists them under their first question."""
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    store.append(
        session.id,
        Event(type=EventType.USER_MESSAGE, session_id=session.id, timestamp=1.0, payload={"content": "fix the bug"}),
    )

    label = SessionPicker.label(store.rebuild(session.id))

    assert "fix the bug" in label
    assert session.id not in label


def test_the_turn_is_told_to_the_terminal(tmp_path):
    """The notification says what the agent answered."""
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"hello")
            await pilot.press("enter")
            assert await _wait_for(lambda: _assistant_blocks(app))

    asyncio.run(go())
    assert app._notification() == "\x1b]777;notify;coder;hello\x07"


def test_a_file_is_completed_in_the_input(tmp_path):
    """The `@` of the input completes the path of a file."""
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    app = _app(tmp_path)
    suggestions = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"look at @READ")
            await asyncio.sleep(0.2)
            suggestions.append(app.query_one(Input)._suggestion)

    asyncio.run(go())
    assert suggestions[0] == "look at @README.md"


def test_the_tree_of_the_files_can_be_shown(tmp_path):
    """`ctrl+t` shows the files of the working directory beside the conversation."""
    (tmp_path / "a.py").write_text("one\n", encoding="utf-8")
    app = _app(tmp_path)

    async def go():
        async with app.run_test() as pilot:
            tree = app.query_one("#files", FileTree)
            assert not tree.display
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert tree.display
            assert "a.py" in [str(node.label) for node in tree.root.children]

    asyncio.run(go())


def test_the_tree_of_the_files_shows_the_directories_that_are_open(tmp_path):
    """`ctrl+t` shows the directories the user opened to the agent, and nothing else."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no\n", encoding="utf-8")
    app = _app(tmp_path, include_dirs=[str(workspace)])

    async def go():
        async with app.run_test() as pilot:
            tree = app.query_one("#files", FileTree)
            await pilot.press("ctrl+t")
            await pilot.pause()
            labels = [str(node.label) for node in tree.root.children]
            assert "note.txt" in labels
            assert "secret.txt" not in labels

    asyncio.run(go())


def test_a_turn_that_was_cut_off_says_why_it_ended(tmp_path):
    """The agent goes quiet at the ceiling of the model calls: the user has to know."""
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "read", "arguments": '{"path": "a.txt"}'},
    }
    app = _app(
        tmp_path,
        responses=[{"role": "assistant", "content": "", "tool_calls": [call], "extra": {"cost": 0.0}}],
        mode="default",
    )
    app.loop.max_turns = 1
    notices = []

    async def go():
        async with app.run_test() as pilot:
            await pilot.press(*"run it")
            await pilot.press("enter")
            assert await _wait_for(lambda: [b for b in app.query(MessageBlock) if b.role == "notice"])
            notices.extend(b for b in app.query(MessageBlock) if b.role == "notice")

    asyncio.run(go())
    assert "ceiling of 1 model calls" in notices[0].content
