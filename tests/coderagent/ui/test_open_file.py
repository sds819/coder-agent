"""The file opener: the editor of the user opens the file."""

import sys
import time
from pathlib import Path

from coderagent.ui.open_file import open_path, opener_command

OPENER = """
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(sys.argv[2], encoding="utf-8")
"""


def test_the_editors_the_user_may_name():
    assert opener_command("vscode", Path("/x/a.py")) == ["code", "-g", "/x/a.py"]
    assert opener_command("cursor", Path("/x/a.py")) == ["cursor", "-g", "/x/a.py"]
    assert opener_command("windsurf", Path("/x/a.py")) == ["windsurf", "-g", "/x/a.py"]


def test_a_command_of_the_user_may_take_the_file():
    assert opener_command("my-editor {file} --wait", Path("/x/a.py")) == ["my-editor", "/x/a.py", "--wait"]


def test_a_command_without_a_placeholder_gets_the_file_at_the_end():
    assert opener_command("my-editor --wait", Path("/x/a.py")) == ["my-editor", "--wait", "/x/a.py"]


def test_without_an_opener_there_is_no_command():
    assert opener_command("", Path("/x/a.py")) == []


def test_a_file_that_is_not_there_is_reported(tmp_path):
    assert "There is no file" in open_path("nope.py", "vscode", tmp_path)


def test_without_an_opener_the_file_is_not_opened(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert "No file opener" in open_path("a.py", "", tmp_path)


def test_the_file_is_opened(tmp_path):
    seen = tmp_path / "seen.txt"
    script = tmp_path / "opener.py"
    script.write_text(OPENER, encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    answer = open_path("a.py", f"{sys.executable} {script} {seen}", tmp_path)

    assert "Opened" in answer
    for _ in range(100):
        if seen.exists():
            break
        time.sleep(0.05)
    assert seen.read_text(encoding="utf-8") == str(tmp_path / "a.py")
