"""Where a skill comes from: the sources, the addresses and the fetches."""

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
from coderagent.skills.source import check_host, check_url, fetch, fetch_registry, parse_source

POLICY = source.Policy(allow_insecure=True, allowed_hosts=("127.0.0.1",))
"""The policy of the tests: the server of the test runs on the machine itself."""


class _Quiet(SimpleHTTPRequestHandler):
    """A handler that says nothing about what it serves."""

    def log_message(self, format, *args):
        pass


class _WithoutLength(_Quiet):
    """A handler that does not say how long its answer is."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(b"x" * 5000)


@contextmanager
def serve(directory: Path, handler=_Quiet):
    """A HTTP server that serves a directory."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _tarball(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return path


def _github(tmp_path: Path, members: dict[str, bytes]) -> Path:
    """A directory that serves a repository the way GitHub does."""
    archive = _tarball(tmp_path / "repo.tar.gz", members)
    served = tmp_path / "served"
    (served / "repos" / "owner" / "repo" / "tarball").mkdir(parents=True)
    (served / "repos" / "owner" / "repo" / "tarball" / "v1").write_bytes(archive.read_bytes())
    return served


def test_a_repository_is_a_github_source():
    assert parse_source("owner/repo") == source.Source(kind="github", repo="owner/repo")
    assert parse_source("owner/repo@v1") == source.Source(kind="github", repo="owner/repo", ref="v1")
    assert parse_source("owner/repo/skills/pdf@v1") == source.Source(
        kind="github", repo="owner/repo", path="skills/pdf", ref="v1"
    )


def test_the_prefix_wins_over_the_shape():
    assert parse_source("github:owner/repo").kind == "github"
    assert parse_source("direct:owner/repo").kind == "direct"
    assert parse_source("registry:owner/repo").kind == "registry"


def test_a_repository_of_gitee_is_a_gitee_source():
    assert parse_source("gitee:owner/repo") == source.Source(kind="gitee", repo="owner/repo")
    assert parse_source("gitee:owner/repo/skills/pdf") == source.Source(
        kind="gitee", repo="owner/repo", path="skills/pdf"
    )


def test_an_address_of_gitee_is_a_gitee_source():
    parsed = parse_source("https://gitee.com/owner/repo/tree/main/skills/pdf")
    assert parsed.kind == "gitee"
    assert parsed.repo == "owner/repo"
    assert parsed.path == "skills/pdf"


def test_a_gitee_source_survives_the_lock_file():
    """The lock file holds the source as it was written down."""
    source_ = parse_source("gitee:owner/repo/skills/pdf")

    assert source.source_of(source_.as_dict()) == source_


def test_a_gitee_source_says_where_it_is_from():
    assert parse_source("gitee:owner/repo/skills/pdf").describe() == "owner/repo/skills/pdf"


def test_an_address_of_a_registry_is_a_registry():
    assert parse_source("https://example.com/index.json").kind == "registry"
    assert parse_source("registry:https://example.com/index.json").url == "https://example.com/index.json"


def test_an_address_of_a_skill_file_is_a_direct_source():
    assert parse_source("https://example.com/pdf/SKILL.md").kind == "direct"


def test_an_address_of_a_repository_is_a_git_source():
    assert parse_source("https://example.com/org/repo.git").kind == "git"
    assert parse_source("git@example.com:org/repo.git").url == "git@example.com:org/repo.git"


def test_an_address_of_github_is_a_github_source():
    parsed = parse_source("https://github.com/owner/repo/tree/v1/skills/pdf")
    assert parsed.kind == "github"
    assert parsed.repo == "owner/repo"
    assert parsed.ref == "v1"
    assert parsed.path == "skills/pdf"


def test_text_that_is_not_a_source_is_refused():
    for text in ("hello", "owner"):
        with pytest.raises(SkillError, match="not a source of a skill"):
            parse_source(text)


def test_an_empty_source_is_refused():
    with pytest.raises(SkillError, match="there is no source"):
        parse_source("")


def test_an_address_that_is_not_a_skill_is_refused():
    with pytest.raises(SkillError, match="does not point at a skill"):
        parse_source("https://example.com/page.html")


def test_only_https_is_fetched():
    with pytest.raises(SkillError, match="only https is allowed"):
        check_url("http://example.com/x", source.Policy())


def test_a_host_inside_the_network_is_refused():
    with pytest.raises(SkillError, match="inside the network"):
        check_host("127.0.0.1", ())


def test_a_host_that_is_allowed_is_not_refused():
    assert check_host("127.0.0.1", ("127.0.0.1",)) is None


def test_a_download_that_is_not_there_is_refused(tmp_path):
    with serve(tmp_path) as base:
        with pytest.raises(SkillError, match="the server said 404"):
            source.download(f"{base}/nope.txt", POLICY)


def test_a_download_that_is_too_big_is_refused(tmp_path):
    with serve(tmp_path, _WithoutLength) as base:
        with pytest.raises(SkillError, match="bigger than 100 bytes"):
            source.download(
                f"{base}/big.txt", source.Policy(allow_insecure=True, allowed_hosts=("127.0.0.1",), max_bytes=100)
            )


def test_a_registry_lists_its_skills(tmp_path):
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "name": "mine",
                "skills": [
                    {"name": "pdf", "description": "Make a PDF", "source": {"kind": "github", "repo": "owner/repo"}},
                    {"name": "broken", "source": {"kind": "nowhere"}},
                ],
            }
        )
    )
    with serve(tmp_path) as base:
        entries = fetch_registry(f"{base}/index.json", POLICY)
    assert [entry.name for entry in entries] == ["pdf"]
    assert entries[0].source.repo == "owner/repo"


def test_a_registry_that_is_not_json_is_refused(tmp_path):
    (tmp_path / "index.json").write_text("not json")
    with serve(tmp_path) as base:
        with pytest.raises(SkillError, match="cannot be read"):
            fetch_registry(f"{base}/index.json", POLICY)


def test_a_skill_is_fetched_from_github(tmp_path, monkeypatch):
    served = _github(tmp_path, {"owner-repo-abc/SKILL.md": b"---\nname: pdf\n---\n"})
    with serve(served) as base:
        monkeypatch.setattr(source, "GITHUB_API", base)
        fetched = fetch(source.Source(kind="github", repo="owner/repo", ref="v1"), tmp_path / "work", POLICY)
    assert (fetched / "SKILL.md").exists()


def test_a_directory_that_is_not_in_the_repository_is_refused(tmp_path, monkeypatch):
    served = _github(tmp_path, {"owner-repo-abc/SKILL.md": b"x"})
    with serve(served) as base:
        monkeypatch.setattr(source, "GITHUB_API", base)
        with pytest.raises(SkillError, match="there is no 'skills/pdf' in owner/repo"):
            fetch(
                source.Source(kind="github", repo="owner/repo", path="skills/pdf", ref="v1"), tmp_path / "work", POLICY
            )


def test_only_the_directory_of_the_skill_is_taken(tmp_path, monkeypatch):
    """A repository is big, a skill is small: the rest of it is left alone."""
    served = _github(
        tmp_path,
        {"owner-repo-abc/skills/pdf/SKILL.md": b"x", "owner-repo-abc/README.md": b"y", "owner-repo-abc/logo.png": b"z"},
    )
    with serve(served) as base:
        monkeypatch.setattr(source, "GITHUB_API", base)
        fetched = fetch(
            source.Source(kind="github", repo="owner/repo", path="skills/pdf", ref="v1"), tmp_path / "work", POLICY
        )
    assert [path.name for path in fetched.iterdir()] == ["SKILL.md"]
