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


def test_the_tree_lists_only_the_directories_that_are_open(tmp_path):
    """The tree shows the directories the user opened to the agent, and nothing else."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no\n", encoding="utf-8")

    tree = FileTree(tmp_path, [workspace])
    tree.reload()

    assert _labels(tree) == ["note.txt"]


def test_every_directory_that_is_open_is_a_node_of_its_own(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    (first / "a.txt").write_text("a\n", encoding="utf-8")
    second = tmp_path / "second"
    second.mkdir()
    (second / "b.txt").write_text("b\n", encoding="utf-8")

    tree = FileTree(tmp_path, [first, second])
    tree.reload()

    assert _labels(tree) == ["first/", "second/"]
    assert [str(child.label) for child in tree.root.children[0].children] == ["a.txt"]


def test_the_path_of_a_file_outside_the_working_directory_is_the_whole_one(tmp_path):
    """The agent can be given the file: the path it gets is one it understands."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello\n", encoding="utf-8")

    tree = FileTree(cwd, [workspace])
    tree.reload()

    assert tree.root.children[0].data == (workspace / "note.txt").as_posix()
