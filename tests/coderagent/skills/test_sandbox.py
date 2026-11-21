"""The boundaries of a downloaded skill: how big, how deep, and where."""

import io
import tarfile
from pathlib import Path

import pytest

from coderagent.skills.errors import SkillError
from coderagent.skills.sandbox import Policy, check_name, check_path, copy_tree, digest, entries_of, unpack_tar

POLICY = Policy()


def _tarball(path: Path, members: dict[str, bytes]) -> Path:
    """A tarball with the given files in it."""
    with tarfile.open(path, "w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return path


def _link(path: Path, name: str, target: str) -> Path:
    """A tarball with a link in it."""
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.type = tarfile.SYMTYPE
        info.linkname = target
        tar.addfile(info)
    return path


def test_a_tarball_is_unpacked(tmp_path):
    archive = _tarball(
        tmp_path / "a.tar.gz", {"owner-repo-abc/SKILL.md": b"hi", "owner-repo-abc/scripts/run.py": b"print(1)"}
    )
    entries = unpack_tar(archive, tmp_path / "out", POLICY)
    assert [entry.path for entry in entries] == ["SKILL.md", "scripts/run.py"]
    assert (tmp_path / "out" / "SKILL.md").read_bytes() == b"hi"


def test_the_directory_of_the_archive_is_dropped(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {"owner-repo-abc/SKILL.md": b"hi"})
    unpack_tar(archive, tmp_path / "out", POLICY)
    assert (tmp_path / "out" / "SKILL.md").exists()
    assert not (tmp_path / "out" / "owner-repo-abc").exists()


def test_an_archive_that_holds_its_own_root_is_unpacked(tmp_path):
    """The tarball of GitHub holds the directory of the repository as a member."""
    archive = tmp_path / "a.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("owner-repo-abc")
        info.type = tarfile.DIRTYPE
        tar.addfile(info)
        for name, content in {"owner-repo-abc/SKILL.md": b"hi", "owner-repo-abc/scripts/run.py": b"print(1)"}.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))

    entries = unpack_tar(archive, tmp_path / "out", POLICY)

    assert [entry.path for entry in entries] == ["SKILL.md", "scripts/run.py"]
    assert (tmp_path / "out" / "SKILL.md").read_bytes() == b"hi"
    assert not (tmp_path / "out" / "owner-repo-abc").exists()


def test_a_plain_file_at_the_top_is_not_a_root(tmp_path):
    """An archive without a directory of its own keeps its paths."""
    archive = _tarball(tmp_path / "a.tar.gz", {"SKILL.md": b"hi"})
    entries = unpack_tar(archive, tmp_path / "out", POLICY)
    assert [entry.path for entry in entries] == ["SKILL.md"]


def test_only_the_directory_that_is_wanted_is_unpacked(tmp_path):
    """A repository is big, a skill is small: the rest of it is left alone."""
    archive = _tarball(
        tmp_path / "a.tar.gz",
        {"owner-repo-abc/skills/pdf/SKILL.md": b"hi", "owner-repo-abc/README.md": b"no"},
    )
    entries = unpack_tar(archive, tmp_path / "out", POLICY, prefix="skills/pdf")
    assert [entry.path for entry in entries] == ["SKILL.md"]
    assert not (tmp_path / "out" / "README.md").exists()


def test_a_path_that_leaves_the_directory_is_refused(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {"repo/../../evil": b"x"})
    with pytest.raises(SkillError, match="not a path inside"):
        unpack_tar(archive, tmp_path / "out", POLICY)


def test_an_absolute_path_is_refused(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {"/etc/passwd": b"x"})
    with pytest.raises(SkillError, match="not a path inside"):
        unpack_tar(archive, tmp_path / "out", POLICY)


def test_a_link_is_refused(tmp_path):
    archive = _link(tmp_path / "a.tar.gz", "repo/passwd", "/etc/passwd")
    with pytest.raises(SkillError, match="not a plain file"):
        unpack_tar(archive, tmp_path / "out", POLICY)


def test_too_many_files_are_refused(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {f"repo/{index}.md": b"x" for index in range(5)})
    with pytest.raises(SkillError, match="more than 2 files"):
        unpack_tar(archive, tmp_path / "out", Policy(max_files=2))


def test_a_file_that_is_too_big_is_refused(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {"repo/big.md": b"x" * 100})
    with pytest.raises(SkillError, match="bigger than 10 bytes"):
        unpack_tar(archive, tmp_path / "out", Policy(max_file_bytes=10))


def test_a_skill_that_is_too_big_is_refused(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {"repo/a.md": b"x" * 60, "repo/b.md": b"x" * 60})
    with pytest.raises(SkillError, match="bigger than 100 bytes"):
        unpack_tar(archive, tmp_path / "out", Policy(max_bytes=100))


def test_a_directory_that_is_too_deep_is_refused(tmp_path):
    archive = _tarball(tmp_path / "a.tar.gz", {"repo/a/b/c/d.md": b"x"})
    with pytest.raises(SkillError, match="deeper than 2 levels"):
        unpack_tar(archive, tmp_path / "out", Policy(max_depth=2))


def test_a_link_of_a_repository_is_refused(tmp_path):
    source = tmp_path / "repo"
    (source / "sub").mkdir(parents=True)
    (source / "sub" / "SKILL.md").write_text("hi")
    (source / "passwd").symlink_to("/etc/passwd")
    with pytest.raises(SkillError, match="is a link"):
        copy_tree(source, tmp_path / "out", POLICY)


def test_a_repository_is_copied(tmp_path):
    source = tmp_path / "repo"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("hi")
    (source / "scripts" / "run.py").write_text("print(1)")
    entries = copy_tree(source, tmp_path / "out", POLICY)
    assert [entry.path for entry in entries] == ["SKILL.md", "scripts/run.py"]
    assert (tmp_path / "out" / "scripts" / "run.py").read_text() == "print(1)"


def test_the_digest_does_not_depend_on_the_order(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    (one / "a").mkdir(parents=True)
    (two / "a").mkdir(parents=True)
    (one / "a" / "x.md").write_text("x")
    (one / "b.md").write_text("y")
    (two / "b.md").write_text("y")
    (two / "a" / "x.md").write_text("x")
    assert digest(entries_of(one)) == digest(entries_of(two))


def test_the_digest_changes_with_the_content(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "a.md").write_text("x")
    (two / "a.md").write_text("z")
    assert digest(entries_of(one)) != digest(entries_of(two))


def test_the_name_of_a_skill_has_to_be_safe():
    assert check_name("pdf-report") == "pdf-report"
    for name in ("..", "a/b", "PDF", "", "-x", "a" * 65):
        with pytest.raises(SkillError, match="not a name a skill can have"):
            check_name(name)


def test_a_path_of_a_windows_reserved_name_is_refused(tmp_path):
    with pytest.raises(SkillError, match="Windows does not allow"):
        check_path(tmp_path, "repo/NUL.md")


def test_a_path_of_a_drive_is_refused(tmp_path):
    with pytest.raises(SkillError, match="not allowed"):
        check_path(tmp_path, "C:/windows/system32")
