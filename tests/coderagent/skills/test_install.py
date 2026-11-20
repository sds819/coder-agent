"""Putting a skill on the disk: the staging, the install and the lock file."""

import io
import json
import tarfile
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from coderagent.skills import source
from coderagent.skills.errors import SkillError
from coderagent.skills.install import check_update, install, read_lock, read_stage, stage, uninstall

SKILL = """---
name: pdf-report
description: Make a PDF report out of a folder of notes.
---

Use `scripts/make_report.py` to build the report.
"""

POLICY = source.Policy(allow_insecure=True, allowed_hosts=("127.0.0.1",))


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@contextmanager
def serve(directory: Path):
    """A HTTP server that serves a directory."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _skill_dir(tmp_path: Path, text: str = SKILL) -> Path:
    """A directory with a skill in it, ready to be served."""
    directory = tmp_path / "served"
    directory.mkdir(exist_ok=True)
    (directory / "SKILL.md").write_text(text)
    return directory


def _github(tmp_path: Path, members: dict[str, bytes]) -> Path:
    """A directory that serves a repository the way GitHub does."""
    archive = tmp_path / "repo.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    served = tmp_path / "github"
    (served / "repos" / "owner" / "repo" / "tarball").mkdir(parents=True)
    (served / "repos" / "owner" / "repo" / "tarball" / "v1").write_bytes(archive.read_bytes())
    return served


def test_a_skill_waits_for_the_user(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    assert staged.name == "pdf-report"
    assert staged.description == "Make a PDF report out of a folder of notes."
    assert "make_report.py" in staged.body
    assert [entry.path for entry in staged.files] == ["SKILL.md"]
    assert staged.sha256
    assert not (tmp_path / "skills" / "pdf-report").exists()


def test_a_staged_skill_is_still_there_afterwards(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    again = read_stage(staged.stage_id, tmp_path)
    assert again.name == staged.name
    assert again.sha256 == staged.sha256
    assert again.source.url == staged.source.url


def test_a_stage_that_is_gone_is_refused(tmp_path):
    with pytest.raises(SkillError, match="the preview is gone"):
        read_stage("nothing", tmp_path)


def test_a_skill_without_a_front_matter_is_refused(tmp_path):
    served = _skill_dir(tmp_path, "Just a note.")
    with serve(served) as base:
        with pytest.raises(SkillError, match="there is no SKILL.md in it"):
            stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    cache = tmp_path / "cache" / "skills"
    assert not cache.exists() or not list(cache.iterdir())


def test_a_name_that_may_not_be_used_is_cleaned(tmp_path):
    served = _skill_dir(tmp_path, SKILL.replace("name: pdf-report", "name: A Report"))
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    assert staged.name == "a-report"
    assert any("not a name a skill can have" in warning for warning in staged.warnings)


def test_a_skill_with_scripts_says_so(tmp_path, monkeypatch):
    served = _github(
        tmp_path, {"owner-repo-abc/SKILL.md": SKILL.encode(), "owner-repo-abc/scripts/run.py": b"print(1)"}
    )
    with serve(served) as base:
        monkeypatch.setattr(source, "GITHUB_API", base)
        staged = stage(source.Source(kind="github", repo="owner/repo", ref="v1"), POLICY, tmp_path)
    assert any("script" in warning for warning in staged.warnings)


def test_a_repository_comes_with_its_files(tmp_path, monkeypatch):
    served = _github(
        tmp_path, {"owner-repo-abc/SKILL.md": SKILL.encode(), "owner-repo-abc/scripts/run.py": b"print(1)"}
    )
    with serve(served) as base:
        monkeypatch.setattr(source, "GITHUB_API", base)
        staged = stage(source.Source(kind="github", repo="owner/repo", ref="v1"), POLICY, tmp_path)
    assert [entry.path for entry in staged.files] == ["SKILL.md", "scripts/run.py"]


def test_an_installed_skill_is_where_the_agent_looks(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    installed = install(staged, tmp_path)
    assert (tmp_path / "skills" / "pdf-report" / "SKILL.md").exists()
    assert installed.sha256 == staged.sha256
    assert installed.source.url == staged.source.url


def test_the_lock_file_says_what_was_installed(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    install(staged, tmp_path)
    lock = read_lock(tmp_path)
    assert lock["pdf-report"].source.kind == "direct"
    assert lock["pdf-report"].files[0].path == "SKILL.md"
    assert json.loads((tmp_path / "skills.lock.json").read_text())["version"] == 1


def test_a_skill_that_is_installed_already_is_refused(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    install(staged, tmp_path)
    with serve(served) as base:
        again = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    with pytest.raises(SkillError, match="is installed already"):
        install(again, tmp_path)


def test_an_installed_skill_is_removed(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    install(staged, tmp_path)
    uninstall("pdf-report", tmp_path)
    assert not (tmp_path / "skills" / "pdf-report").exists()
    assert read_lock(tmp_path) == {}


def test_a_skill_of_the_user_is_not_removed(tmp_path):
    (tmp_path / "skills" / "mine").mkdir(parents=True)
    (tmp_path / "skills" / "mine" / "SKILL.md").write_text(SKILL)
    with pytest.raises(SkillError, match="it is yours"):
        uninstall("mine", tmp_path)
    assert (tmp_path / "skills" / "mine" / "SKILL.md").exists()


def test_the_stage_is_gone_after_the_install(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    install(staged, tmp_path)
    assert not (tmp_path / "cache" / "skills" / staged.stage_id).exists()


def test_a_lock_file_that_cannot_be_read_says_so(tmp_path):
    (tmp_path / "skills.lock.json").write_text("not json")
    with pytest.raises(SkillError, match="skills.lock.json cannot be read"):
        read_lock(tmp_path)


def test_a_skill_that_did_not_change_has_no_update(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
        installed = install(staged, tmp_path)
        assert check_update(installed, POLICY, tmp_path) is None


def test_a_skill_that_changed_has_an_update(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
        installed = install(staged, tmp_path)
        (served / "SKILL.md").write_text(SKILL.replace("notes", "papers"))
        update = check_update(installed, POLICY, tmp_path)
    assert update is not None
    assert update.sha256 != installed.sha256


def test_an_update_replaces_the_old_one(tmp_path):
    served = _skill_dir(tmp_path)
    with serve(served) as base:
        staged = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    install(staged, tmp_path)
    (served / "SKILL.md").write_text(SKILL.replace("notes", "papers"))
    with serve(served) as base:
        update = stage(source.Source(kind="direct", url=f"{base}/SKILL.md"), POLICY, tmp_path)
    with pytest.raises(SkillError, match="is installed already"):
        install(update, tmp_path)
    install(update, tmp_path, force=True)
    assert "papers" in (tmp_path / "skills" / "pdf-report" / "SKILL.md").read_text()
