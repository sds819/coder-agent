"""The `/image` command: an image goes to the model with the text that goes with it."""

import base64
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

ONE_PIXEL_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


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


def _png(tmp_path: Path) -> Path:
    path = tmp_path / "shot.png"
    path.write_bytes(base64.b64decode(ONE_PIXEL_PNG))
    return path


def test_the_image_goes_to_the_model_with_the_text(tmp_path):
    context, output, submitted = _context(tmp_path)
    _png(tmp_path)
    assert run(context, "/image shot.png what is this") is True
    assert output == []
    assert submitted[0][0] == {"type": "text", "text": "what is this"}
    assert submitted[0][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_an_image_without_a_text_is_still_an_image(tmp_path):
    context, output, submitted = _context(tmp_path)
    _png(tmp_path)
    assert run(context, "/image shot.png") is True
    assert len(submitted[0]) == 1
    assert submitted[0][0]["type"] == "image_url"


def test_the_command_says_which_image_it_wants(tmp_path):
    context, output, submitted = _context(tmp_path)
    assert run(context, "/image") is True
    assert "Which image?" in output[0]
    assert submitted == []


def test_a_file_that_is_not_an_image_is_refused(tmp_path):
    context, output, submitted = _context(tmp_path)
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    assert run(context, "/image notes.txt") is True
    assert "not an image" in output[0]
    assert submitted == []


def test_an_image_that_is_not_there_is_refused(tmp_path):
    context, output, submitted = _context(tmp_path)
    assert run(context, "/image missing.png") is True
    assert "missing.png" in output[0]
    assert submitted == []
