import os
import time

import pytest

from coderagent.testing.factory import build_context
from coderagent.tools.builtin.shell import (
    BashKillTool,
    BashOutputTool,
    BashTool,
    CodingEnvironment,
    _reap_at_exit,
    reap_background,
    trim_output,
)


class Container:
    """An environment that is not local: the commands run somewhere else."""

    def __init__(self, cwd):
        self.cwd = cwd

    def execute(self, action, cwd="", timeout=30):
        return {"output": "in the container", "returncode": 0}


@pytest.fixture
def ctx(tmp_path):
    return build_context(tmp_path)


def test_bash_returns_the_command_output(ctx):
    result = BashTool().run({"command": "echo hello"}, ctx)
    assert result.content.strip() == "hello"
    assert not result.is_error


def test_bash_reports_a_failing_command(ctx):
    result = BashTool().run({"command": "exit 3"}, ctx)
    assert result.is_error
    assert "exit code 3" in result.content


def test_bash_runs_in_the_working_directory(ctx, tmp_path):
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    assert "marker.txt" in BashTool().run({"command": "ls"}, ctx).content


def test_bash_kills_a_command_that_runs_too_long(ctx):
    started = time.time()
    result = BashTool().run({"command": "sleep 30", "timeout": 1}, ctx)
    assert time.time() - started < 10
    assert result.is_error
    assert "timed out" in result.content.lower() or "timeout" in result.content.lower()


def test_bash_trims_long_output(ctx):
    result = BashTool().run({"command": "for i in $(seq 1 20000); do echo 0123456789; done"}, ctx)
    assert "tokens elided" in result.content


def test_trim_output_keeps_the_head_and_the_tail():
    trimmed = trim_output("a" * 100 + "b" * 100, 4)
    assert "tokens elided" in trimmed
    assert trimmed.startswith("a")
    assert trimmed.endswith("b")


def test_bash_rejects_an_empty_command(ctx):
    assert BashTool().run({"command": "  "}, ctx).is_error


def test_the_coding_environment_ignores_the_submission_sentinel(tmp_path):
    env = CodingEnvironment(cwd=str(tmp_path))
    output = env.execute({"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"})
    assert output["returncode"] == 0
    assert "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in output["output"]


def test_a_background_task_can_be_read_and_killed(ctx):
    started = BashTool().run({"command": "sleep 30", "run_in_background": True}, ctx)
    task_id = started.metadata["task_id"]

    output = BashOutputTool().run({"task_id": task_id}, ctx)
    assert "running" in output.content

    assert "Killed" in BashKillTool().run({"task_id": task_id}, ctx).content
    assert "exited" in BashOutputTool().run({"task_id": task_id}, ctx).content


def test_the_background_tasks_are_reaped(ctx):
    """A background task belongs to the session that started it."""
    started = BashTool().run({"command": "sleep 30", "run_in_background": True}, ctx)
    task = ctx.background[started.metadata["task_id"]]
    directory = task["log"].parent
    assert directory.exists()

    reap_background([task])
    assert task["process"].poll() is not None
    assert not directory.exists()


def test_no_background_task_outlives_the_process(ctx):
    """Nothing of a session stays behind when the process ends."""
    started = BashTool().run({"command": "sleep 30", "run_in_background": True}, ctx)
    task = ctx.background[started.metadata["task_id"]]
    _reap_at_exit()
    assert task["process"].poll() is not None


def test_the_background_tools_reject_unknown_tasks(ctx):
    assert BashOutputTool().run({"task_id": "nope"}, ctx).is_error
    assert BashKillTool().run({"task_id": "nope"}, ctx).is_error


def test_a_background_task_does_not_run_outside_the_environment(ctx, tmp_path):
    """A container cannot start a command in the background, so it is refused.

    Otherwise the command would run on the machine of the user, outside of the
    boundary of the session.
    """
    marker = tmp_path / "marker.txt"
    ctx.env = Container(tmp_path)
    result = BashTool().run({"command": f"touch {marker}", "run_in_background": True}, ctx)
    assert result.is_error
    assert "outside of it" in result.content
    time.sleep(0.5)
    assert not marker.exists()


def test_a_background_task_runs_with_the_environment_of_the_session(ctx, tmp_path, monkeypatch):
    """The command gets the environment of the session, not the one of the user."""
    monkeypatch.setenv("CODERAGENT_SECRET", "leak")
    env = CodingEnvironment(cwd=str(tmp_path))
    env.env_override = {key: value for key, value in os.environ.items() if key != "CODERAGENT_SECRET"}
    ctx.env = env
    started = BashTool().run({"command": "echo [$CODERAGENT_SECRET]", "run_in_background": True}, ctx)
    time.sleep(0.5)
    output = BashOutputTool().run({"task_id": started.metadata["task_id"]}, ctx).content
    assert "[]" in output


def test_a_running_command_is_stopped_when_the_turn_is_interrupted(ctx):
    ctx.cancel = lambda: True
    started = time.time()
    result = BashTool().run({"command": "sleep 30"}, ctx)
    assert time.time() - started < 10
    assert "[interrupted]" in result.content
    assert not result.is_error


def test_the_children_of_an_interrupted_command_are_stopped(ctx, tmp_path):
    marker = tmp_path / "marker.txt"
    ctx.cancel = lambda: True
    BashTool().run({"command": f"sleep 1; touch {marker}"}, ctx)
    time.sleep(1.5)
    assert not marker.exists()


def test_the_output_of_a_command_that_is_not_interrupted_is_kept(ctx):
    ctx.cancel = lambda: False
    result = BashTool().run({"command": "echo before"}, ctx)
    assert "before" in result.content
    assert "[interrupted]" not in result.content
