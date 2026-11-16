"""The completion of a file path after an `@`."""

import asyncio

from coderagent.ui.widgets.path_suggester import PathSuggester


def _suggest(tmp_path, value: str) -> str | None:
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    return asyncio.run(PathSuggester(tmp_path).get_suggestion(value))


def test_a_file_is_completed(tmp_path):
    assert _suggest(tmp_path, "@README") == "@README.md"


def test_the_text_before_the_at_is_kept(tmp_path):
    assert _suggest(tmp_path, "look at @READ") == "look at @README.md"


def test_a_directory_is_completed_to_the_file_in_it(tmp_path):
    assert _suggest(tmp_path, "@src/app") == "@src/app.py"


def test_nothing_without_an_at(tmp_path):
    assert _suggest(tmp_path, "README") is None


def test_an_at_inside_a_word_is_not_a_path(tmp_path):
    assert _suggest(tmp_path, "write to me@example") is None


def test_a_path_that_does_not_exist_is_not_suggested(tmp_path):
    assert _suggest(tmp_path, "@nothing") is None


def test_the_hidden_directories_are_left_out(tmp_path):
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".git" / "config.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    suggester = PathSuggester(tmp_path)
    assert "a.py" in suggester.paths()
    assert ".git/config.py" not in suggester.paths()
