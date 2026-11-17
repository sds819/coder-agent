"""Instruction files: the user level, the project level and the lazy subdirectory level."""

from pathlib import Path

from coderagent.config.schema import ContextConfig
from coderagent.core.context import ContextEngine
from coderagent.core.events import EventBus
from coderagent.core.instructions import load_instructions, subdirectory_instructions
from coderagent.core.session import SessionStore


def test_the_user_instructions_come_first(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "CLAUDE.md").write_text("the user rules", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("the project rules", encoding="utf-8")
    blocks = load_instructions(tmp_path, home)
    assert [block.source for block in blocks] == ["CLAUDE.md", "AGENTS.md"]
    assert blocks[0].content == "the user rules"


def test_both_project_files_are_loaded(tmp_path):
    (tmp_path / "AGENTS.md").write_text("the agent rules", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("the claude rules", encoding="utf-8")
    blocks = load_instructions(tmp_path, tmp_path / "home")
    assert [block.content for block in blocks] == ["the agent rules", "the claude rules"]


def test_missing_and_empty_files_are_skipped(tmp_path):
    (tmp_path / "AGENTS.md").write_text("   \n", encoding="utf-8")
    assert load_instructions(tmp_path, tmp_path / "home") == []


def test_a_block_renders_with_its_source(tmp_path):
    (tmp_path / "AGENTS.md").write_text("the rules", encoding="utf-8")
    block = load_instructions(tmp_path, tmp_path / "home")[0]
    assert block.render() == ('<project_instructions source="AGENTS.md">\nthe rules\n</project_instructions>')


def test_the_subdirectory_instructions_are_deepest_first(tmp_path):
    deep = tmp_path / "src" / "core"
    deep.mkdir(parents=True)
    (tmp_path / "src" / "AGENTS.md").write_text("the src rules", encoding="utf-8")
    (deep / "AGENTS.md").write_text("the core rules", encoding="utf-8")
    blocks = subdirectory_instructions(deep / "module.py", tmp_path)
    assert [block.content for block in blocks] == ["the core rules", "the src rules"]


def test_a_file_in_the_root_has_no_subdirectory_instructions(tmp_path):
    (tmp_path / "AGENTS.md").write_text("the root rules", encoding="utf-8")
    assert subdirectory_instructions(tmp_path / "module.py", tmp_path) == []


def test_a_path_outside_the_project_has_no_instructions(tmp_path):
    assert subdirectory_instructions(Path("/etc/hosts"), tmp_path) == []


def _engine(tmp_path, config: ContextConfig | None = None):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    return ContextEngine(
        session,
        store,
        EventBus(),
        config or ContextConfig(),
        None,
        cwd=tmp_path,
        user_home=tmp_path / "home",
    )


def test_touching_a_file_picks_up_the_instructions_of_its_directory(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "AGENTS.md").write_text("the src rules", encoding="utf-8")
    engine = _engine(tmp_path)
    assert engine._instruction_text() == ""
    engine.note_path(str(tmp_path / "src" / "module.py"))
    assert "the src rules" in engine._instruction_text()


def test_the_same_file_is_only_injected_once(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "AGENTS.md").write_text("the src rules", encoding="utf-8")
    engine = _engine(tmp_path)
    engine.note_path(str(tmp_path / "src" / "one.py"))
    engine.note_path(str(tmp_path / "src" / "two.py"))
    assert engine._instruction_text().count("the src rules") == 1


def test_a_relative_path_is_resolved_against_the_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "AGENTS.md").write_text("the src rules", encoding="utf-8")
    engine = _engine(tmp_path)
    engine.note_path("src/module.py")
    assert "the src rules" in engine._instruction_text()


def test_the_instruction_files_are_read_again_when_they_change(tmp_path):
    """The rules of the project may change while the session runs."""
    (tmp_path / "AGENTS.md").write_text("the first rules", encoding="utf-8")
    engine = _engine(tmp_path)
    assert "the first rules" in engine._instruction_text()
    (tmp_path / "AGENTS.md").write_text("the second rules", encoding="utf-8")
    assert "the second rules" in engine._instruction_text()


def test_the_instructions_of_the_caller_are_not_read_again(tmp_path):
    """The instructions that were given explicitly stay the ones that were given."""
    from coderagent.core.instructions import InstructionBlock

    (tmp_path / "AGENTS.md").write_text("the project rules", encoding="utf-8")
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    engine = ContextEngine(
        session,
        store,
        EventBus(),
        ContextConfig(),
        None,
        cwd=tmp_path,
        user_home=tmp_path / "home",
        instructions=[InstructionBlock(source="given.md", content="the given rules", path=tmp_path / "given.md")],
    )
    text = engine._instruction_text()
    assert "the given rules" in text
    assert "the project rules" not in text


def test_a_file_that_is_too_long_is_cut_short(tmp_path):
    """The instructions of the project may not take the whole context."""
    (tmp_path / "AGENTS.md").write_text("x" * 5000, encoding="utf-8")
    block = load_instructions(tmp_path, tmp_path / "home", 1000)[0]
    assert len(block.content) < 1200
    assert "the rest of it is not shown" in block.content


def test_a_file_that_fits_is_not_cut(tmp_path):
    (tmp_path / "AGENTS.md").write_text("the rules", encoding="utf-8")
    assert load_instructions(tmp_path, tmp_path / "home", 1000)[0].content == "the rules"


def test_the_rules_of_the_repository_are_found_from_a_subdirectory(tmp_path):
    """An agent that starts in a subdirectory still has to see the rules of the repository."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("the rules of the repository", encoding="utf-8")
    sub = tmp_path / "src" / "core"
    sub.mkdir(parents=True)
    blocks = load_instructions(sub, tmp_path / "home")
    assert [block.content for block in blocks] == ["the rules of the repository"]


def test_the_rules_of_the_repository_come_before_the_rules_of_the_directory(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("the rules of the repository", encoding="utf-8")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "AGENTS.md").write_text("the rules of the directory", encoding="utf-8")
    blocks = load_instructions(sub, tmp_path / "home")
    assert [block.content for block in blocks] == [
        "the rules of the repository",
        "the rules of the directory",
    ]


def test_a_directory_outside_a_repository_is_its_own_root(tmp_path):
    (tmp_path / "AGENTS.md").write_text("the rules", encoding="utf-8")
    blocks = load_instructions(tmp_path, tmp_path / "home")
    assert [block.content for block in blocks] == ["the rules"]


def test_the_rules_of_the_root_are_not_read_twice(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("the rules", encoding="utf-8")
    blocks = load_instructions(tmp_path, tmp_path / "home")
    assert [block.content for block in blocks] == ["the rules"]


def test_the_limit_of_the_configuration_holds(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x" * 5000, encoding="utf-8")
    engine = _engine(tmp_path, ContextConfig(project_doc_max_bytes=1000))
    assert "the rest of it is not shown" in engine._instruction_text()
