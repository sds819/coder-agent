"""The built-in slash commands."""

import sys
from pathlib import Path

import pytest

from coderagent.config.schema import Config
from coderagent.core.checkpoint import CheckpointStore
from coderagent.core.events import EventBus
from coderagent.core.loop import AgentLoop
from coderagent.core.session import SessionStore
from coderagent.core.subagent import SubagentSpec, load_subagents
from coderagent.models.gateway import ModelGateway
from coderagent.models.router import ModelRouter
from coderagent.skills.install import Installed, write_lock
from coderagent.skills.source import Source
from coderagent.testing.factory import build_executor
from coderagent.testing.scripted_model import ScriptedModel
from coderagent.tools.permissions import PermissionMode, PermissionPolicy
from coderagent.ui.commands import COMMANDS, CommandContext, find, load_builtins, run


def _context(tmp_path, responses=None) -> tuple[CommandContext, list[str]]:
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    bus = EventBus()
    executor = build_executor(tmp_path)
    loop = AgentLoop(
        ModelGateway(ScriptedModel(responses or [{"role": "assistant", "content": "ok"}])),
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
        subagents=load_subagents(tmp_path),
        router=ModelRouter(Config().model),
    )
    output: list[str] = []
    context = CommandContext(
        loop=loop,
        session=session,
        store=store,
        bus=bus,
        cwd=Path(tmp_path),
        config=Config(),
        policy=PermissionPolicy(PermissionMode.DEFAULT, [], cwd=Path(tmp_path)),
        output=output.append,
    )
    return context, output


def _run(context: CommandContext, output: list[str], line: str) -> str:
    assert run(context, line) is True
    return "\n".join(output)


def test_there_are_enough_commands():
    load_builtins()
    assert len(COMMANDS) >= 18
    assert find("/help") is not None
    assert find("m") is not None
    assert find("nope") is None


def test_a_line_that_is_not_a_command_is_not_a_command(tmp_path):
    context, output = _context(tmp_path)
    assert run(context, "just a message") is False
    assert output == []


def test_an_unknown_command_says_so(tmp_path):
    context, output = _context(tmp_path)
    assert "Unknown command" in _run(context, output, "/nope")


def test_help_lists_the_commands(tmp_path):
    context, output = _context(tmp_path)
    assert "/compact" in _run(context, output, "/help")


def test_help_describes_one_command(tmp_path):
    context, output = _context(tmp_path)
    assert "Compact the conversation" in _run(context, output, "/help compact")


def test_the_help_shows_what_the_commands_take(tmp_path):
    """The options of a command are part of the help, not a thing to remember."""
    context, output = _context(tmp_path)
    answer = _run(context, output, "/help")
    assert "[default|acceptEdits|plan|bypass|readonly]" in answer
    assert "[name]" in answer


def test_the_help_of_one_command_shows_what_it_takes(tmp_path):
    context, output = _context(tmp_path)
    assert "takes: [default|acceptEdits|plan|bypass|readonly]" in _run(context, output, "/help mode")


def test_the_mode_says_which_modes_it_takes(tmp_path):
    context, output = _context(tmp_path)
    answer = _run(context, output, "/mode")
    assert "mode: default" in answer
    assert "acceptEdits" in answer


def test_the_help_lists_the_commands_of_the_project(tmp_path):
    context, output = _context(tmp_path)
    directory = tmp_path / ".coderagent" / "commands"
    directory.mkdir(parents=True)
    (directory / "commit.md").write_text(
        "---\ndescription: Write a commit message\nargument-hint: [file]\n---\nDescribe the change of $1.",
        encoding="utf-8",
    )
    answer = _run(context, output, "/help")
    assert "/commit" in answer
    assert "Write a commit message" in answer
    assert "[file]" in answer


def test_the_help_of_a_command_of_the_project(tmp_path):
    context, output = _context(tmp_path)
    directory = tmp_path / ".coderagent" / "commands"
    directory.mkdir(parents=True)
    (directory / "commit.md").write_text(
        "---\ndescription: Write a commit message\nargument-hint: [file]\n---\nDescribe the change of $1.",
        encoding="utf-8",
    )
    answer = _run(context, output, "/help commit")
    assert "Write a commit message" in answer
    assert "takes: [file]" in answer


def test_status_shows_the_session(tmp_path):
    context, output = _context(tmp_path)
    assert context.session.id in _run(context, output, "/status")


def test_the_mode_can_be_switched(tmp_path):
    context, output = _context(tmp_path)
    _run(context, output, "/mode plan")
    assert context.policy.mode == PermissionMode.PLAN
    assert context.session.permission_mode == "plan"


def test_an_unknown_mode_is_refused(tmp_path):
    context, output = _context(tmp_path)
    assert "Unknown mode" in _run(context, output, "/mode nope")
    assert context.policy.mode == PermissionMode.DEFAULT


def test_the_plan_command_switches_to_plan(tmp_path):
    context, output = _context(tmp_path)
    _run(context, output, "/plan")
    assert context.policy.mode == PermissionMode.PLAN


def test_the_model_is_shown_and_can_be_switched(tmp_path):
    context, output = _context(tmp_path)
    context.config.model.model_name = "deepseek/deepseek-flash"
    assert "deepseek/deepseek-flash" in _run(context, output, "/model")
    _run(context, output, "/model other/model")
    assert context.config.model.model_name == "other/model"
    assert context.loop.model.backend.model_name == "other/model"


def test_the_model_the_user_picks_wins_over_the_routing(tmp_path):
    context, output = _context(tmp_path)
    _run(context, output, "/model my/model")
    assert context.loop.router.resolve("main", {"tokens": 999999}) == "my/model"


def test_the_model_command_answers_with_the_name_the_session_calls(tmp_path):
    """The name of the user may be shorter than the one litellm is called with."""
    context, output = _context(tmp_path)
    assert "model: openai/gpt-4o" in _run(context, output, "/model gpt-4o")


def test_the_thinking_budget_is_shown_and_survives_a_switch_of_the_model(tmp_path):
    context, output = _context(tmp_path)
    context.config.model.reasoning_effort = "high"

    assert "effort: high" in _run(context, output, "/model")

    _run(context, output, "/model other/model")
    assert context.loop.model.backend.model_kwargs["reasoning_effort"] == "high"


def test_the_todos_are_shown(tmp_path):
    context, output = _context(tmp_path)
    context.session.metadata["todos"] = [{"content": "write the code", "status": "in_progress"}]
    assert "write the code" in _run(context, output, "/todos")


def test_the_cost_is_shown(tmp_path):
    context, output = _context(tmp_path)
    assert "cost so far" in _run(context, output, "/cost")


def test_the_cost_of_a_model_without_a_price_is_unknown(tmp_path):
    """A model without a price spends no money: the cost is unknown, not zero."""

    class UnpricedModel(ScriptedModel):
        priced = False

    context, output = _context(tmp_path)
    context.loop.model.backend = UnpricedModel([{"role": "assistant", "content": "ok"}])

    text = _run(context, output, "/cost")

    assert "cost so far: $?" in text
    assert "no price" in text


def test_compact_shrinks_the_context(tmp_path):
    context, output = _context(tmp_path)
    for index in range(30):
        context.loop.context.append({"role": "user", "content": f"question {index}"})
        context.loop.context.append({"role": "assistant", "content": f"answer {index}"})
    assert "Compacted" in _run(context, output, "/compact")
    assert context.loop.context.summary is not None


def test_compact_says_when_there_is_nothing_to_compact(tmp_path):
    context, output = _context(tmp_path)
    assert "Nothing to compact" in _run(context, output, "/compact")


def test_recap_summarizes_the_conversation_without_changing_it(tmp_path):
    context, output = _context(
        tmp_path,
        [
            {"role": "assistant", "content": "ok"},
            {"role": "assistant", "content": '{"goal": "the goal"}'},
        ],
    )
    context.loop.run_turn("hello")
    before = list(context.loop.context.history.messages)
    assert "goal: the goal" in _run(context, output, "/recap")
    assert context.loop.context.history.messages == before
    assert context.loop.context.summary is None


def test_recap_says_when_there_is_nothing_to_summarize(tmp_path):
    context, output = _context(tmp_path)
    assert "Nothing to summarize" in _run(context, output, "/recap")


def test_side_asks_for_a_question(tmp_path):
    context, output = _context(tmp_path)
    assert "What do you want to ask" in _run(context, output, "/side")


def test_side_says_when_the_interface_cannot_run_a_turn(tmp_path):
    context, output = _context(tmp_path)
    assert "cannot run a turn" in _run(context, output, "/side what does this do?")


def test_side_starts_a_conversation_of_its_own(tmp_path):
    context, output = _context(tmp_path)
    asked = []
    context.submit_side = lambda text, session: asked.append((text, session))
    before = list(context.loop.context.history.messages)
    assert "side conversation" in _run(context, output, "/side what does this do?")
    assert asked[0][0] == "what does this do?"
    assert asked[0][1].metadata["parent"] == context.session.id
    assert context.loop.context.history.messages == before


def test_clear_starts_a_new_session(tmp_path):
    context, output = _context(tmp_path)
    before = context.session.id
    _run(context, output, "/clear")
    assert context.session.id != before
    assert context.loop.session.id == context.session.id


def test_the_new_session_of_clear_pays_nothing_of_the_old_one(tmp_path):
    """The money of the session before `/clear` stays with that session."""
    context, output = _context(
        tmp_path,
        [
            {"role": "assistant", "content": "ok", "extra": {"cost": 0.5}},
            {"role": "assistant", "content": "no facts", "extra": {"cost": 0.2}},
            {"role": "assistant", "content": "ok", "extra": {"cost": 0.3}},
        ],
    )
    context.loop.run("hi")
    assert context.session.total_cost == pytest.approx(0.5)

    _run(context, output, "/clear")
    context.loop.run("again")
    assert context.session.total_cost == pytest.approx(0.3)
    assert context.store.rebuild(context.session.id).total_cost == pytest.approx(0.3)


def test_resume_lists_the_sessions(tmp_path):
    context, output = _context(tmp_path)
    assert context.session.id in _run(context, output, "/resume")


def test_resume_switches_to_the_session(tmp_path):
    context, output = _context(tmp_path)
    other = context.store.create(tmp_path)
    _run(context, output, f"/resume {other.id}")
    assert context.loop.session.id == other.id


def test_fork_copies_the_session(tmp_path):
    context, output = _context(tmp_path)
    before = context.session.id
    _run(context, output, "/fork")
    assert context.session.id != before
    assert context.loop.session.id == context.session.id
    assert len(context.store.list(tmp_path)) == 2


def test_rewind_lists_the_checkpoints(tmp_path):
    context, output = _context(tmp_path)
    context.checkpoints = CheckpointStore(root=tmp_path / "checkpoints")
    assert "No checkpoints" in _run(context, output, "/rewind")


def test_rewind_says_when_there_are_no_checkpoints_at_all(tmp_path):
    context, output = _context(tmp_path)
    assert "not available" in _run(context, output, "/rewind")


def test_diff_says_when_it_is_not_a_repository(tmp_path):
    context, output = _context(tmp_path)
    assert "Not a git repository" in _run(context, output, "/diff")


def test_init_writes_the_instruction_file(tmp_path):
    context, output = _context(tmp_path)
    _run(context, output, "/init")
    assert "AGENTS.md" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


def test_init_does_not_overwrite_an_existing_file(tmp_path):
    context, output = _context(tmp_path)
    (tmp_path / "AGENTS.md").write_text("mine", encoding="utf-8")
    assert "already exists" in _run(context, output, "/init")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine"


def test_export_writes_the_conversation(tmp_path):
    context, output = _context(tmp_path)
    context.loop.context.append({"role": "user", "content": "hello there"})
    _run(context, output, "/export")
    assert "hello there" in (tmp_path / "conversation.md").read_text(encoding="utf-8")


def test_the_permissions_are_shown(tmp_path):
    context, output = _context(tmp_path)
    assert "mode: default" in _run(context, output, "/permissions")


def test_no_hooks_are_configured(tmp_path):
    context, output = _context(tmp_path)
    assert "No hooks" in _run(context, output, "/hooks")


def test_no_mcp_servers_are_configured(tmp_path):
    context, output = _context(tmp_path)
    assert "No MCP servers" in _run(context, output, "/mcp")


def test_the_context_size_is_shown(tmp_path):
    context, output = _context(tmp_path)
    assert "tokens" in _run(context, output, "/context")


def test_the_sub_agents_are_shown(tmp_path):
    context, output = _context(tmp_path)
    answer = _run(context, output, "/agents")
    assert "code-explorer" in answer
    assert "verifier" in answer
    assert "read, grep" in answer


def test_the_agents_show_the_turns_that_count(tmp_path):
    """The turns of the sub agent, held down by the ceiling of the configuration."""
    context, output = _context(tmp_path)
    answer = _run(context, output, "/agents")
    assert "(15 model calls)" in answer
    assert "holds every sub agent" not in answer


def test_the_ceiling_of_the_configuration_shows_up(tmp_path):
    context, output = _context(tmp_path)
    context.config.agent.subagent_max_turns = 20
    answer = _run(context, output, "/agents")
    assert "(20 model calls)" in answer
    assert "holds every sub agent to 20 model calls" in answer


def test_a_sub_agent_without_a_limit_shows_no_limit(tmp_path):
    context, output = _context(tmp_path)
    context.loop.subagents = {"free": SubagentSpec(name="free", description="Runs as long as it wants.", max_turns=0)}
    answer = _run(context, output, "/agents")
    assert "(no limit)" in answer


def test_the_skills_are_shown(tmp_path):
    context, output = _context(tmp_path)
    directory = tmp_path / ".coderagent" / "skills" / "pdf-report"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: pdf-report\ndescription: Make a PDF report.\n---\nMake it.", encoding="utf-8"
    )
    answer = _run(context, output, "/skills")
    assert "pdf-report" in answer
    assert "Make a PDF report." in answer


def test_the_skills_say_where_they_came_from(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("MSWEA_CODER_HOME", str(home))
    context, output = _context(tmp_path)
    directory = home / "skills" / "pdf-report"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: pdf-report\ndescription: Make a PDF report.\n---\nMake it.", encoding="utf-8"
    )
    write_lock(
        {
            "pdf-report": Installed(
                name="pdf-report",
                source=Source(kind="github", repo="owner/repo", ref="v1"),
                sha256="9f2c" + "0" * 60,
                installed_at="2026-11-20T10:00:00Z",
            )
        },
        home,
    )
    answer = _run(context, output, "/skills")
    assert "owner/repo@v1" in answer
    assert "9f2c" in answer


def test_a_skill_of_the_user_says_nothing_about_a_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    directory = tmp_path / ".coderagent" / "skills" / "pdf-report"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: pdf-report\ndescription: Make a PDF report.\n---\nMake it.", encoding="utf-8"
    )
    answer = _run(context, output, "/skills")
    assert "pdf-report" in answer
    assert "sha256" not in answer


def test_the_plugins_are_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    directory = tmp_path / ".coderagent" / "plugins" / "hello"
    directory.mkdir(parents=True)
    (directory / "plugin.py").write_text("def register(registry):\n    pass\n", encoding="utf-8")
    answer = _run(context, output, "/plugins")
    assert "hello" in answer
    assert "not trusted" in answer


def test_a_plugin_can_be_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    directory = tmp_path / ".coderagent" / "plugins" / "hello"
    directory.mkdir(parents=True)
    (directory / "plugin.py").write_text("def register(registry):\n    pass\n", encoding="utf-8")
    assert "Trusted" in _run(context, output, "/plugins trust hello")
    assert (tmp_path / "home" / "trusted-plugins.json").exists()


def test_the_code_of_the_project_that_waits_is_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    _project_hook(tmp_path, "python lint.py")
    answer = _run(context, output, "/trust")
    assert "python lint.py" in answer
    assert "hook" in answer


def test_nothing_waits_when_the_project_has_no_code(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    assert "Nothing of the project waits" in _run(context, output, "/trust")


def test_the_code_of_the_project_can_be_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    _project_hook(tmp_path, "python lint.py")
    assert "Trusted" in _run(context, output, "/trust 1")
    assert (tmp_path / "home" / "trusted.json").exists()
    assert "Nothing of the project waits" in _run(context, output, "/trust")


def test_a_number_that_is_not_one_of_them_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MSWEA_CODER_HOME", str(tmp_path / "home"))
    context, output = _context(tmp_path)
    _project_hook(tmp_path, "python lint.py")
    assert "is not one of the numbers" in _run(context, output, "/trust 9")
    assert not (tmp_path / "home" / "trusted.json").exists()


def _project_hook(project: Path, command: str) -> None:
    """A project with a hook, whose code waits for a decision of the user."""
    directory = project / ".coderagent"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.yaml").write_text(
        f"hooks:\n  events:\n    PreToolUse:\n      - matcher: bash\n        hooks:\n          - command: {command}\n",
        encoding="utf-8",
    )


def test_the_sandbox_is_shown(tmp_path):
    context, output = _context(tmp_path)
    answer = _run(context, output, "/sandbox")
    assert "type: local" in answer
    assert "environment: local" in answer


def test_the_options_of_the_sandbox_are_shown(tmp_path):
    """The options that are in effect are shown, the ones that are not are not there."""
    context, output = _context(tmp_path)
    context.config.sandbox.image = "python:3.11"
    answer = _run(context, output, "/sandbox")
    assert "image: python:3.11" in answer


def test_the_cost_is_attributed(tmp_path):
    context, output = _context(tmp_path)
    context.loop.run("hi")
    answer = _run(context, output, "/cost")
    assert "by purpose:" in answer
    assert "main" in answer


def test_the_memory_is_shown(tmp_path):
    context, output = _context(tmp_path)
    memory = tmp_path / ".coderagent" / "memory"
    memory.mkdir(parents=True)
    (memory / "projects.md").write_text("# Project memory\n\n- the build is make build\n", encoding="utf-8")
    answer = _run(context, output, "/memory")
    assert "the build is make build" in answer
    assert "pending preferences" in answer


def test_a_fact_can_be_forgotten(tmp_path):
    context, output = _context(tmp_path)
    memory = tmp_path / ".coderagent" / "memory"
    memory.mkdir(parents=True)
    (memory / "projects.md").write_text("# Project memory\n\n- the build is make build\n", encoding="utf-8")
    assert "Removed" in _run(context, output, "/memory forget the build is make build")
    assert "make build" not in (memory / "projects.md").read_text(encoding="utf-8")


def test_the_exit_command_leaves_the_interface(tmp_path):
    context, output = _context(tmp_path)
    left: list[bool] = []
    context.quit = lambda: left.append(True)
    _run(context, output, "/exit")
    assert left == [True]
    assert output == []


def test_the_exit_command_says_so_when_there_is_nothing_to_leave(tmp_path):
    context, output = _context(tmp_path)
    assert "ctrl+c" in _run(context, output, "/exit")


def test_quit_is_an_alias_of_exit(tmp_path):
    context, output = _context(tmp_path)
    left: list[bool] = []
    context.quit = lambda: left.append(True)
    _run(context, output, "/quit")
    assert left == [True]


def test_the_session_can_be_named(tmp_path):
    context, output = _context(tmp_path)
    assert "name: the bug" in _run(context, output, "/rename the bug")
    assert context.session.name == "the bug"
    assert context.store.rebuild(context.session.id).name == "the bug"


def test_the_name_of_the_session_is_shown(tmp_path):
    context, output = _context(tmp_path)
    _run(context, output, "/rename the bug")
    assert "the bug" in _run(context, output, "/rename")


def test_a_session_can_be_put_away_and_taken_out(tmp_path):
    context, output = _context(tmp_path)
    assert "Archived" in _run(context, output, "/archive")
    assert context.store.rebuild(context.session.id).archived is True
    assert "Took out" in _run(context, output, "/archive")
    assert context.store.rebuild(context.session.id).archived is False


def test_a_session_that_is_not_there_cannot_be_put_away(tmp_path):
    context, output = _context(tmp_path)
    assert "No session" in _run(context, output, "/archive nope")


def test_a_session_can_be_deleted(tmp_path):
    context, output = _context(tmp_path)
    other = context.store.create(tmp_path)
    assert f"Deleted {other.id}" in _run(context, output, f"/delete {other.id}")
    assert context.store.events(other.id) == []


def test_the_session_you_are_in_cannot_be_deleted(tmp_path):
    context, output = _context(tmp_path)
    assert "You are in this session" in _run(context, output, f"/delete {context.session.id}")


def test_a_session_that_is_not_there_cannot_be_deleted(tmp_path):
    context, output = _context(tmp_path)
    assert "No session" in _run(context, output, "/delete nope")


def test_the_delete_command_says_which_session_it_wants(tmp_path):
    context, output = _context(tmp_path)
    assert "/delete <session-id>" in _run(context, output, "/delete")


def test_a_file_is_opened_in_the_editor_of_the_user(tmp_path):
    context, output = _context(tmp_path)
    seen = tmp_path / "seen.txt"
    script = tmp_path / "opener.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n",
        encoding="utf-8",
    )
    context.config.ui.file_opener = f"{sys.executable} {script} {seen}"
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    assert "Opened" in _run(context, output, "/open a.py")


def test_a_file_outside_the_working_directory_is_not_opened(tmp_path):
    context, output = _context(tmp_path)
    context.config.ui.file_opener = "vscode"
    outside = tmp_path.parent / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    assert "outside the working directory" in _run(context, output, f"/open {outside}")


def test_without_an_opener_the_file_is_not_opened(tmp_path):
    context, output = _context(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert "No file opener" in _run(context, output, "/open a.py")


def test_bypass_mode_asks_before_it_is_switched_on(tmp_path):
    """Bypass takes the guards off: it is not switched on by a slip of the fingers."""
    context, output = _context(tmp_path)

    answer = _run(context, output, "/mode bypass")

    assert context.policy.mode == PermissionMode.DEFAULT
    assert "/mode bypass --yes" in answer


def test_bypass_mode_is_switched_on_when_it_is_confirmed(tmp_path):
    context, output = _context(tmp_path)

    _run(context, output, "/mode bypass --yes")

    assert context.policy.mode == PermissionMode.BYPASS
    assert context.session.permission_mode == "bypass"
