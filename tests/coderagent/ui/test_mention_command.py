"""The `/mention` command: a file goes to the model with the text that goes with it."""

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


def _context(tmp_path: Path) -> tuple[CommandContext, list[str], list]:
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    executor = build_executor(tmp_path)
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
    submitted: list = []
    context = CommandContext(
        loop=loop,
        session=session,
        store=store,
        bus=loop.bus,
        cwd=tmp_path,
        config=Config(),
        policy=PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path),
        output=output.append,
        submit=submitted.append,
    )
    return context, output, submitted


def test_the_file_goes_to_the_model_with_the_text(tmp_path):
    context, output, submitted = _context(tmp_path)
    (tmp_path / "a.py").write_text("print('hi')\n", encoding="utf-8")
    assert run(context, "/mention a.py what does this do") is True
    assert output == []
    assert submitted[0] == "what does this do\n\n@a.py"


def test_a_file_without_a_text_still_goes(tmp_path):
    context, output, submitted = _context(tmp_path)
    (tmp_path / "a.py").write_text("print('hi')\n", encoding="utf-8")
    assert run(context, "/mention a.py") is True
    assert submitted[0] == "@a.py"


def test_the_command_says_which_file_it_wants(tmp_path):
    context, output, submitted = _context(tmp_path)
    assert run(context, "/mention") is True
    assert "Which file?" in output[0]
    assert submitted == []
