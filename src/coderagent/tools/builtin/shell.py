"""Shell tool: `bash` plus the background task helpers `bash_output` and `bash_kill`."""

import atexit
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from coderagent.core.tokens import trim_text
from coderagent.tools.base import ToolContext, ToolResult
from minisweagent.environments.local import LocalEnvironment

CHARS_PER_TOKEN = 3.5
POLL_SECONDS = 0.05
"""How often a running command is asked whether the turn is still going on."""

_TASKS: list[dict] = []
"""The background tasks of this process. None of them outlives it."""


class CodingEnvironment(LocalEnvironment):
    """Local environment without mini-swe-agent's `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` magic.

    A coding agent ends a turn when the model says so, not when a shell command prints a
    sentinel string.
    """

    def _check_finished(self, output: dict) -> None:
        return None

    def execute_cancellable(self, action: dict, cwd: str = "", *, timeout: int = 30, cancel=None) -> dict:
        """Run a command that can be stopped while it runs.

        The turn can be interrupted while a command is running. The command is then
        killed, together with the children it started, and the output it produced so
        far is returned. A command in a remote sandbox cannot be killed, which is why
        this is here and not in the environment of mini-swe-agent.
        """
        command = action.get("command", "")
        cwd = cwd or self.config.cwd or os.getcwd()
        process = subprocess.Popen(  # noqa: S602
            command,
            shell=True,
            text=True,
            cwd=cwd,
            env=self.environment(),
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        text, interrupted, timed_out = self._drain(process, timeout, cancel)
        if interrupted:
            return {"output": text, "returncode": -1, "interrupted": True, "exception_info": ""}
        if timed_out:
            return {
                "output": text,
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: Command '{command}' timed out after {timeout} seconds",
            }
        return {"output": text, "returncode": process.returncode, "exception_info": ""}

    def _drain(self, process, timeout: int, cancel) -> tuple[str, bool, bool]:
        """Read the output of a command until it ends, is interrupted or times out."""
        collected: list[str] = []
        reader = threading.Thread(target=lambda: collected.append(process.stdout.read() or ""), daemon=True)
        reader.start()
        deadline = time.time() + timeout
        interrupted = False
        timed_out = False
        while process.poll() is None:
            if cancel is not None and cancel():
                interrupted = True
                _kill(process)
                break
            if time.time() >= deadline:
                timed_out = True
                _kill(process)
                break
            time.sleep(POLL_SECONDS)
        reader.join(timeout=2)
        return "".join(collected), interrupted, timed_out


def _kill(process) -> None:
    """Stop a command and the children it started."""
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        """The command ended by itself between the check and the kill."""
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()


def reap_background(tasks: list[dict]) -> None:
    """Stop the background tasks and take their logs away.

    A task that still runs is killed, together with the children it started,
    and the directory of its log goes away with it. A background task belongs
    to the session that started it: it does not outlive the process.
    """
    for task in tasks:
        if task["process"].poll() is None:
            _kill(task["process"])
        try:
            task["handle"].close()
        except (OSError, ValueError):
            """The handle is already closed."""
            pass
        shutil.rmtree(task["log"].parent, ignore_errors=True)
    tasks.clear()


@atexit.register
def _reap_at_exit() -> None:
    """Nothing of a session stays behind when the process ends."""
    reap_background(_TASKS)


def trim_output(text: str, max_output_tokens: int) -> str:
    """Keep the head and the tail of long output, elide the middle."""
    return trim_text(text, max_output_tokens)[0]


def read_head_and_tail(path: Path, limit: int) -> str:
    """The head and the tail of a file, without reading all of it.

    A background task may print a lot. Its log is not read into memory just to
    show the ends of it.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    if size <= limit:
        return path.read_text(encoding="utf-8", errors="replace")
    half = limit // 2
    with path.open("rb") as handle:
        head = handle.read(half)
        handle.seek(-half, os.SEEK_END)
        tail = handle.read()
    return (
        f"{head.decode('utf-8', 'replace')}\n"
        f"... [the middle of the log is not shown] ...\n"
        f"{tail.decode('utf-8', 'replace')}"
    )


def _confined(command: str, ctx: ToolContext) -> str:
    """The command with the sandbox of the operating system in front of it.

    The permission layer has already had its say on the command itself, so the
    sandbox only gets to hold the line where the disk and the network are.
    """
    if ctx.sandbox is None:
        return command
    return ctx.sandbox.wrap(command)


class BashTool:
    name = "bash"
    description = (
        "Run a shell command in the working directory. Use it for pipelines, builds and tests; "
        "use the dedicated file tools for reading and editing files. The commands that only look "
        "around go through; the ones that destroy something or send it out ask for approval, and "
        "a path outside the working directory is refused."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to run."},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Defaults to the configured timeout."},
            "run_in_background": {
                "type": "boolean",
                "description": "Start the command and return a task id at once. Only a local environment can do this.",
            },
        },
        "required": ["command"],
    }

    def run(self, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = params.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolResult("Error: `command` is required and must be a non-empty string.", is_error=True)
        timeout = params.get("timeout")
        timeout = int(timeout) if isinstance(timeout, int) and timeout > 0 else ctx.config.bash_timeout
        if params.get("run_in_background"):
            return self._start_background(command, ctx)

        env = ctx.env if hasattr(ctx.env, "execute") else CodingEnvironment(cwd=str(ctx.cwd))
        """A remote sandbox has its own working directory, the path of the host means nothing there."""
        cwd = str(ctx.cwd) if isinstance(env, LocalEnvironment) else ""
        result = self._execute(env, _confined(command, ctx), cwd, timeout, ctx)
        output = str(result.get("output", ""))
        content = trim_output(output, ctx.config.max_output_tokens)
        returncode = result.get("returncode", 0)
        interrupted = bool(result.get("interrupted"))
        if interrupted:
            content = f"{content}\n[interrupted]".strip()
        elif result.get("exception_info"):
            content = f"{content}\n{result['exception_info']}".strip()
        elif returncode != 0:
            content = f"{content}\n[exit code {returncode}]".strip()
        return ToolResult(
            content,
            is_error=returncode != 0 and not interrupted,
            metadata={"returncode": returncode, "interrupted": interrupted},
        )

    def _execute(self, env, command: str, cwd: str, timeout: int, ctx: ToolContext) -> dict:
        """Run the command, and stop it when the turn is interrupted.

        A command that runs on this machine can be killed. A command in a remote
        sandbox cannot, so there the turn stops after the command is done.
        """
        if ctx.cancel is not None and isinstance(env, CodingEnvironment):
            return env.execute_cancellable({"command": command}, cwd=cwd, timeout=timeout, cancel=ctx.cancel)
        return env.execute({"command": command}, cwd=cwd, timeout=timeout)

    def _start_background(self, command: str, ctx: ToolContext) -> ToolResult:
        """Start a command that goes on while the agent does something else.

        The command runs in the environment of the session. A container cannot
        start a command in the background, so it is refused there: the command
        would run on the machine of the user, outside of the boundary of the
        session.
        """
        env = ctx.env if hasattr(ctx.env, "execute") else CodingEnvironment(cwd=str(ctx.cwd))
        if not isinstance(env, LocalEnvironment):
            return ToolResult(
                "Error: a background task cannot run in this environment: it would run outside of it. "
                "Run the command in the foreground instead.",
                is_error=True,
            )
        task_id = uuid.uuid4().hex[:8]
        directory = Path(tempfile.mkdtemp(prefix="coderagent-bg-"))
        log_path = directory / "output.log"
        handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(  # noqa: S602
            _confined(command, ctx),
            shell=True,
            text=True,
            cwd=str(ctx.cwd),
            env=env.environment(),
            encoding="utf-8",
            errors="replace",
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        task = {"process": process, "handle": handle, "log": log_path, "command": command}
        ctx.background[task_id] = task
        _TASKS.append(task)
        return ToolResult(
            f"Started background task {task_id}: {command}\nUse `bash_output` with task_id={task_id} to check it.",
            metadata={"task_id": task_id},
        )


class BashOutputTool:
    name = "bash_output"
    description = "Show the output collected so far by a background bash task."
    parameters = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The id returned when the task was started."},
        },
        "required": ["task_id"],
    }

    def run(self, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        task = ctx.background.get(str(params.get("task_id", "")))
        if task is None:
            return ToolResult(f"Error: unknown task id '{params.get('task_id')}'.", is_error=True)
        process = task["process"]
        limit = int(ctx.config.max_output_tokens * CHARS_PER_TOKEN)
        output = read_head_and_tail(task["log"], limit)
        status = "running" if process.poll() is None else f"exited with code {process.returncode}"
        content = trim_output(output, ctx.config.max_output_tokens)
        return ToolResult(f"{content}\n[status: {status}]", metadata={"status": status})


class BashKillTool:
    name = "bash_kill"
    description = "Kill a running background bash task."
    parameters = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The id returned when the task was started."},
        },
        "required": ["task_id"],
    }

    def run(self, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        task_id = str(params.get("task_id", ""))
        task = ctx.background.get(task_id)
        if task is None:
            return ToolResult(f"Error: unknown task id '{task_id}'.", is_error=True)
        process = task["process"]
        if process.poll() is None:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
        task["handle"].close()
        return ToolResult(f"Killed background task {task_id}.")


def wait_for_background(task: dict, timeout: float = 5.0) -> None:
    """Wait a bit for a background task to finish. Used by tests."""
    deadline = time.time() + timeout
    while time.time() < deadline and task["process"].poll() is None:
        time.sleep(0.05)
