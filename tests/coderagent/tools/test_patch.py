"""The `apply_patch` tool: a patch with context changes the files it names."""

import pytest

from coderagent.testing.factory import build_context
from coderagent.tools.builtin.patch import ApplyPatchTool, parse_patch, preview
from coderagent.tools.permissions import PermissionMode, PermissionPolicy


@pytest.fixture
def ctx(tmp_path):
    return build_context(tmp_path)


def _patch(*lines: str) -> str:
    return "\n".join(["*** Begin Patch", *lines, "*** End Patch"])


def test_a_patch_changes_the_lines_it_names(ctx, tmp_path):
    (tmp_path / "a.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    result = ApplyPatchTool().run({"patch": _patch("*** Update File: a.py", "@@", " alpha", "-beta", "+delta")}, ctx)
    assert not result.is_error
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "alpha\ndelta\ngamma\n"
    assert "-beta" in result.metadata["diff"]


def test_a_patch_adds_and_deletes_files(ctx, tmp_path):
    (tmp_path / "old.txt").write_text("bye\n", encoding="utf-8")
    result = ApplyPatchTool().run({"patch": _patch("*** Add File: new.txt", "+hello", "*** Delete File: old.txt")}, ctx)
    assert not result.is_error
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "hello\n"
    assert not (tmp_path / "old.txt").exists()


def test_a_patch_that_does_not_fit_changes_nothing(ctx, tmp_path):
    (tmp_path / "a.py").write_text("alpha\n", encoding="utf-8")
    result = ApplyPatchTool().run({"patch": _patch("*** Update File: a.py", "@@", "-nowhere", "+something")}, ctx)
    assert result.is_error
    assert "does not match" in result.content
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "alpha\n"


def test_a_patch_may_not_touch_a_file_outside_the_working_directory(ctx, tmp_path):
    result = ApplyPatchTool().run({"patch": _patch("*** Update File: ../outside.py", "@@", "-a", "+b")}, ctx)
    assert result.is_error
    assert "outside the working directory" in result.content


def test_a_patch_without_the_markers_is_refused(ctx):
    result = ApplyPatchTool().run({"patch": "just some text"}, ctx)
    assert result.is_error
    assert "must start with" in result.content


def test_a_patch_that_does_not_end_is_refused(ctx):
    result = ApplyPatchTool().run({"patch": "*** Begin Patch\n*** Add File: a.txt\n+hello"}, ctx)
    assert result.is_error
    assert "must end with" in result.content


def test_the_tool_says_which_files_the_patch_touches(ctx):
    assert ApplyPatchTool().touched_paths({"patch": _patch("*** Add File: a.txt", "+hello")}) == ["a.txt"]
    assert ApplyPatchTool().touched_paths({"patch": "nonsense"}) == []


def test_the_parser_reads_the_hunks(ctx):
    patches = parse_patch(_patch("*** Update File: a.py", "@@ def main():", " keep", "-old", "+new"))
    assert patches[0].action == "update"
    assert patches[0].path == "a.py"
    assert patches[0].hunks[0].header == "def main():"
    assert patches[0].hunks[0].lines == [" keep", "-old", "+new"]


def test_the_preview_shows_the_diff_without_changing_anything(tmp_path):
    (tmp_path / "a.py").write_text("alpha\nbeta\n", encoding="utf-8")
    diff = preview(_patch("*** Update File: a.py", "@@", "-beta", "+delta"), tmp_path)
    assert "-beta" in diff and "+delta" in diff
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "alpha\nbeta\n"


def test_the_read_only_sandbox_refuses_the_patch(tmp_path):
    from coderagent.core.os_sandbox import READ_ONLY

    policy = PermissionPolicy(PermissionMode.BYPASS, [], cwd=tmp_path, sandbox_mode=READ_ONLY)
    decision = policy.evaluate("apply_patch", {"patch": "*** Begin Patch\n*** End Patch"})
    assert decision.decision == "deny"
    assert "read only" in decision.reason
