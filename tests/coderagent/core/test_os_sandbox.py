"""The sandbox of the operating system: the boundary the commands cannot cross."""

import shlex

import pytest
from pydantic import ValidationError

from coderagent.config.schema import SandboxConfig
from coderagent.core.os_sandbox import (
    FULL_ACCESS,
    READ_ONLY,
    WORKSPACE_WRITE,
    Confinement,
    UnsupportedSandbox,
    find_tool,
    sandbox_block,
)
from coderagent.core.sandbox import describe
from coderagent.tools.builtin.shell import BashTool, CodingEnvironment
from coderagent.tools.permissions import PermissionMode, PermissionPolicy, Rule


def _run(confinement: Confinement, cwd, command: str) -> str:
    """The output of a command that runs inside the sandbox."""
    environment = CodingEnvironment(cwd=str(cwd))
    return str(environment.execute({"command": confinement.wrap(command)})["output"])


def _sandbox_works(confinement: Confinement, cwd) -> bool:
    """Whether the sandbox of this machine runs at all."""
    try:
        return "hello" in _run(confinement, cwd, "echo hello")
    except UnsupportedSandbox:
        return False


@pytest.fixture
def work(tmp_path):
    """A working directory with a scratch directory next to it."""
    (tmp_path / "work").mkdir()
    (tmp_path / "scratch").mkdir()
    return tmp_path


def test_the_full_access_mode_leaves_the_command_alone(tmp_path):
    assert Confinement(FULL_ACCESS, tmp_path).wrap("ls -la") == "ls -la"


def test_the_commands_go_into_the_sandbox_of_the_operating_system(tmp_path):
    wrapped = Confinement(WORKSPACE_WRITE, tmp_path).wrap("ls -la")
    assert "sandbox-exec" in wrapped or "bwrap" in wrapped
    assert "/bin/sh -c" in wrapped


def test_the_command_goes_to_the_sandbox_as_one_argument(tmp_path):
    """A pipeline that was parsed outside the sandbox would run half of it outside."""
    command = "cat a | cat > b"
    assert Confinement(WORKSPACE_WRITE, tmp_path).wrap(command).endswith(f"/bin/sh -c {shlex.quote(command)}")


def test_the_working_directory_may_be_written(work):
    confinement = Confinement(WORKSPACE_WRITE, work / "work", scratch=work / "scratch")
    if not _sandbox_works(confinement, work / "work"):
        pytest.skip("the sandbox of this machine does not run")
    _run(confinement, work / "work", "echo hello > file.txt")
    assert (work / "work" / "file.txt").read_text(encoding="utf-8").strip() == "hello"


def test_a_write_outside_the_working_directory_is_refused(work):
    confinement = Confinement(WORKSPACE_WRITE, work / "work", scratch=work / "scratch")
    if not _sandbox_works(confinement, work / "work"):
        pytest.skip("the sandbox of this machine does not run")
    output = _run(confinement, work / "work", "echo hello > ../outside.txt")
    assert not (work / "outside.txt").exists()
    assert "not permitted" in output or "denied" in output or "Read-only" in output


def test_the_read_only_mode_refuses_to_write(work):
    confinement = Confinement(READ_ONLY, work / "work", scratch=work / "scratch")
    if not _sandbox_works(confinement, work / "work"):
        pytest.skip("the sandbox of this machine does not run")
    _run(confinement, work / "work", "echo hello > file.txt")
    assert not (work / "work" / "file.txt").exists()


def test_the_read_only_mode_may_still_use_the_scratch_directory(work):
    confinement = Confinement(READ_ONLY, work / "work", scratch=work / "scratch")
    if not _sandbox_works(confinement, work / "work"):
        pytest.skip("the sandbox of this machine does not run")
    _run(confinement, work / "work", "echo hello > ../scratch/file.txt")
    assert (work / "scratch" / "file.txt").read_text(encoding="utf-8").strip() == "hello"


def test_the_extra_directory_may_be_written(work):
    (work / "extra").mkdir()
    confinement = Confinement(WORKSPACE_WRITE, work / "work", [str(work / "extra")], scratch=work / "scratch")
    if not _sandbox_works(confinement, work / "work"):
        pytest.skip("the sandbox of this machine does not run")
    _run(confinement, work / "work", "echo hello > ../extra/file.txt")
    assert (work / "extra" / "file.txt").exists()


def test_the_bash_tool_runs_the_commands_in_the_sandbox(work):
    from coderagent.testing.factory import build_context

    confinement = Confinement(WORKSPACE_WRITE, work / "work", scratch=work / "scratch")
    if not _sandbox_works(confinement, work / "work"):
        pytest.skip("the sandbox of this machine does not run")
    context = build_context(work / "work")
    context.sandbox = confinement
    BashTool().run({"command": "echo hello > file.txt"}, context)
    assert (work / "work" / "file.txt").exists()


def test_the_write_tools_are_refused_in_the_read_only_mode(tmp_path):
    policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path, sandbox_mode=READ_ONLY)
    assert policy.check("write", {"path": "file.txt"}) == "deny"
    assert policy.check("edit", {"path": "file.txt"}) == "deny"
    assert policy.check("read", {"path": "file.txt"}) == "allow"


def test_a_rule_of_the_user_cannot_open_the_read_only_sandbox(tmp_path):
    """The rules of the user cannot widen the boundary, like they cannot widen the paths."""
    policy = PermissionPolicy(
        PermissionMode.DEFAULT,
        [Rule(tool="write", pattern="*", decision="allow")],
        cwd=tmp_path,
        sandbox_mode=READ_ONLY,
    )
    assert policy.check("write", {"path": "file.txt"}) == "deny"


def test_the_model_is_told_about_the_sandbox():
    assert "<sandbox" in sandbox_block(WORKSPACE_WRITE)
    assert "working directory" in sandbox_block(WORKSPACE_WRITE)


def test_the_model_is_not_told_about_a_sandbox_that_is_not_there():
    assert sandbox_block(FULL_ACCESS) == ""


def test_the_sandbox_is_named_in_the_interface():
    assert describe(None, "local", WORKSPACE_WRITE) == "local/workspace-write"
    assert describe(None, "local", FULL_ACCESS) == "local"


def test_the_mode_that_does_not_exist_is_refused():
    with pytest.raises(ValidationError, match="unknown sandbox mode"):
        SandboxConfig(mode="sandwich")


def test_a_system_without_a_sandbox_cannot_keep_the_promise():
    with pytest.raises(UnsupportedSandbox, match="not supported"):
        find_tool("Windows", READ_ONLY)
