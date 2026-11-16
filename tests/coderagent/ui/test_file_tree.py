"""The tree of the files of the working directory."""

import subprocess

from coderagent.ui.widgets.file_tree import FileTree, changed_files


def _git(cwd, *args) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _labels(tree: FileTree) -> list[str]:
    return [str(node.label) for node in tree.root.children]


def test_the_tree_shows_the_files_of_the_working_directory(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    tree = FileTree(tmp_path)
    tree.reload()
    assert "README.md" in _labels(tree)
    assert "src/" in _labels(tree)


def test_the_tree_marks_the_files_that_changed(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "test")
    (tmp_path / "a.py").write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-m", "first")
    (tmp_path / "a.py").write_text("two\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("three\n", encoding="utf-8")

    changes = changed_files(tmp_path)
    assert changes.get("a.py") == "M"
    assert changes.get("new.py") == "??"

    tree = FileTree(tmp_path)
    tree.reload()
    assert "● a.py" in _labels(tree)
    assert "? new.py" in _labels(tree)


def test_the_tree_of_a_directory_without_git_shows_the_files(tmp_path):
    (tmp_path / "a.py").write_text("one\n", encoding="utf-8")
    tree = FileTree(tmp_path)
    tree.reload()
    assert _labels(tree) == ["a.py"]


def test_the_tree_is_hidden_until_it_is_asked_for(tmp_path):
    assert not FileTree(tmp_path).display
