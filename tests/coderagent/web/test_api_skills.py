"""The skills of the web interface: the list, the preview and the install."""

import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from coderagent.skills import sites
from coderagent.skills.sites import Site
from coderagent.web import skills_api

SKILL = """---
name: pdf-report
description: Make a PDF report out of a folder of notes.
---

Use `scripts/make_report.py` to build the report.
"""

NETWORK = """
skills:
  allow_insecure: true
  allowed_hosts:
    - 127.0.0.1
"""


class _Quiet(SimpleHTTPRequestHandler):
    """A handler that says nothing about what it serves."""

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


@pytest.fixture
def home(tmp_path, monkeypatch):
    """The directory of the user, away from the one of the machine."""
    path = tmp_path / "home"
    monkeypatch.setenv("MSWEA_CODER_HOME", str(path))
    return path


@pytest.fixture
def served(tmp_path):
    """A directory with a skill in it, ready to be served."""
    directory = tmp_path / "served"
    directory.mkdir(exist_ok=True)
    (directory / "SKILL.md").write_text(SKILL)
    return directory


def test_the_page_is_there(make_client):
    client = make_client()

    answer = client.get("/skills")

    assert answer.status_code == 200
    assert "Skills" in answer.text


def test_the_page_is_in_the_navigation(make_client):
    client = make_client()

    assert '<a href="/skills">Skills</a>' in client.get("/").text
    assert '<a href="/skills">技能</a>' in client.get("/?lang=zh").text


def test_no_skills_are_installed(make_client, home):
    client = make_client()

    answer = client.get("/api/skills")

    assert answer.status_code == 200
    assert answer.json()["skills"] == []


def test_the_skills_that_come_with_the_agent_are_listed(make_client, home):
    """The page shows the skills of the agent next to the installed ones."""
    client = make_client()

    skills = client.get("/api/skills").json()["builtin"]

    assert [skill["name"] for skill in skills][:2] == ["code-review", "codebase-onboarding"]
    assert all(skill["description"] for skill in skills)
    assert all(skill["files"] >= 1 for skill in skills)


def test_a_skill_of_the_user_replaces_the_one_of_the_agent(make_client, home):
    """A skill of the user with the same name is no longer one of the agent."""
    (home / "skills" / "writing").mkdir(parents=True)
    (home / "skills" / "writing" / "SKILL.md").write_text(SKILL.replace("pdf-report", "writing"))
    client = make_client()

    builtin = client.get("/api/skills").json()["builtin"]

    assert "writing" not in [skill["name"] for skill in builtin]


def test_the_text_of_a_skill_of_the_agent_is_there(make_client, home):
    """The details of a skill of the agent can be read."""
    client = make_client()

    answer = client.get("/api/skills/deep-research")

    assert answer.status_code == 200
    assert answer.json()["name"] == "deep-research"
    assert "research/report.md" in answer.json()["body"]


def test_a_skill_of_the_user_is_listed(make_client, home):
    (home / "skills" / "mine").mkdir(parents=True)
    (home / "skills" / "mine" / "SKILL.md").write_text(SKILL)
    client = make_client()

    skill = client.get("/api/skills").json()["skills"][0]

    assert skill["name"] == "mine"
    assert skill["description"] == "Make a PDF report out of a folder of notes."
    assert skill["managed"] is False
    assert skill["source"] == {}


def test_a_skill_that_came_from_the_network_says_where_it_came_from(make_client, home, served):
    client = make_client(project_config=NETWORK)
    with serve(served) as base:
        staged = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        client.post("/api/skills/install", json={"stage_id": staged["stage_id"]})

    skill = client.get("/api/skills").json()["skills"][0]

    assert skill["managed"] is True
    assert skill["source"]["kind"] == "direct"
    assert skill["sha256"] == staged["sha256"]
    assert skill["files"] == 1


def test_the_preview_shows_the_whole_skill(make_client, home, served):
    client = make_client(project_config=NETWORK)

    with serve(served) as base:
        answer = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"})

    preview = answer.json()
    assert answer.status_code == 200
    assert preview["name"] == "pdf-report"
    assert preview["description"] == "Make a PDF report out of a folder of notes."
    assert "make_report.py" in preview["body"]
    assert [entry["path"] for entry in preview["files"]] == ["SKILL.md"]
    assert preview["sha256"]


def test_the_preview_installs_nothing(make_client, home, served):
    client = make_client(project_config=NETWORK)

    with serve(served) as base:
        client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"})

    assert not (home / "skills" / "pdf-report").exists()


def test_a_write_without_the_header_is_refused(make_client, home, served):
    client = make_client(project_config=NETWORK)

    with serve(served) as base:
        answer = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}, headers={"X-Coder-Client": ""})

    assert answer.status_code == 403


def test_a_source_that_is_not_a_source_is_refused(make_client, home):
    client = make_client(project_config=NETWORK)

    answer = client.post("/api/skills/preview", json={"source": "hello"})

    assert answer.status_code == 400
    assert "not a source of a skill" in answer.json()["detail"]


def test_the_reason_is_in_the_language_of_the_visitor(make_client, home):
    client = make_client(project_config=NETWORK)

    answer = client.post("/api/skills/preview?lang=zh", json={"source": "hello"})

    assert answer.status_code == 400
    assert answer.json()["detail"] == "这不是一个技能的来源：hello"


def test_the_reason_of_a_refusal_is_in_the_language_of_the_visitor(make_client, home):
    (home / "skills" / "mine").mkdir(parents=True)
    (home / "skills" / "mine" / "SKILL.md").write_text(SKILL)
    client = make_client()

    answer = client.delete("/api/skills/mine?lang=zh")

    assert answer.status_code == 403
    assert answer.json()["detail"] == "mine 不是这里装的，是你自己的"


def test_the_install_puts_the_skill_where_the_agent_looks(make_client, home, served):
    client = make_client(project_config=NETWORK)
    with serve(served) as base:
        staged = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        answer = client.post("/api/skills/install", json={"stage_id": staged["stage_id"]})

    assert answer.status_code == 200
    assert (home / "skills" / "pdf-report" / "SKILL.md").read_text() == SKILL


def test_a_preview_that_is_gone_is_refused(make_client, home):
    client = make_client(project_config=NETWORK)

    answer = client.post("/api/skills/install", json={"stage_id": "nothing"})

    assert answer.status_code == 400
    assert "the preview is gone" in answer.json()["detail"]


def test_a_skill_that_is_installed_already_is_refused(make_client, home, served):
    client = make_client(project_config=NETWORK)
    with serve(served) as base:
        staged = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        client.post("/api/skills/install", json={"stage_id": staged["stage_id"]})
        again = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        answer = client.post("/api/skills/install", json={"stage_id": again["stage_id"]})

    assert answer.status_code == 409
    assert "force=true" in answer.json()["detail"]


def test_a_skill_of_the_user_is_not_removed(make_client, home):
    (home / "skills" / "mine").mkdir(parents=True)
    (home / "skills" / "mine" / "SKILL.md").write_text(SKILL)
    client = make_client()

    answer = client.delete("/api/skills/mine")

    assert answer.status_code == 403
    assert (home / "skills" / "mine" / "SKILL.md").exists()


def test_an_installed_skill_is_removed(make_client, home, served):
    client = make_client(project_config=NETWORK)
    with serve(served) as base:
        staged = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        client.post("/api/skills/install", json={"stage_id": staged["stage_id"]})

    answer = client.delete("/api/skills/pdf-report")

    assert answer.status_code == 200
    assert not (home / "skills" / "pdf-report").exists()


def test_a_name_that_is_no_name_is_refused(make_client, home):
    client = make_client()

    assert client.get("/api/skills/PDF").status_code == 400
    assert client.delete("/api/skills/PDF").status_code == 400


def test_a_skill_that_did_not_change_has_no_update(make_client, home, served):
    client = make_client(project_config=NETWORK)
    with serve(served) as base:
        staged = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        client.post("/api/skills/install", json={"stage_id": staged["stage_id"]})
        answer = client.post("/api/skills/update", json={"name": "pdf-report"})

    assert answer.status_code == 200
    assert answer.json()["up_to_date"] is True


def test_a_skill_that_changed_has_an_update(make_client, home, served):
    client = make_client(project_config=NETWORK)
    with serve(served) as base:
        staged = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"}).json()
        client.post("/api/skills/install", json={"stage_id": staged["stage_id"]})
        (served / "SKILL.md").write_text(SKILL.replace("notes", "papers"))
        answer = client.post("/api/skills/update", json={"name": "pdf-report"})

    assert answer.status_code == 200
    assert answer.json()["up_to_date"] is False
    assert answer.json()["preview"]["sha256"] != staged["sha256"]


def test_a_registry_lists_its_skills(make_client, home, tmp_path):
    (tmp_path / "index.json").write_text(
        '{"name": "mine", "skills": [{"name": "pdf", "description": "Make a PDF",'
        ' "source": {"kind": "github", "repo": "owner/repo"}}]}'
    )
    client = make_client(project_config=NETWORK)

    with serve(tmp_path) as base:
        answer = client.post("/api/skills/registry", json={"url": f"{base}/index.json"})

    skills = answer.json()["skills"]
    assert answer.status_code == 200
    assert [skill["name"] for skill in skills] == ["pdf"]
    assert skills[0]["source_text"] == "owner/repo"


def test_the_skills_can_be_turned_off(make_client, home, served):
    client = make_client(project_config="skills:\n  enabled: false\n")

    with serve(served) as base:
        answer = client.post("/api/skills/preview", json={"source": f"{base}/SKILL.md"})

    assert answer.status_code == 403
    assert "turned off" in answer.json()["detail"]


def test_the_sites_are_listed(make_client, home):
    """There is a tab for each site."""
    client = make_client()

    answer = client.get("/api/skills/sites")

    listed = answer.json()["sites"]
    assert answer.status_code == 200
    assert len(listed) == 3
    assert [site["id"] for site in listed] == ["official", "personal", "tools"]
    assert all(site["repo"].count("/") == 1 for site in listed)
    assert all(site["url"].startswith("https://gitee.com/") for site in listed)


def test_a_site_that_is_not_there_is_refused(make_client, home):
    """The address of a site may name one that does not exist."""
    client = make_client()

    answer = client.get("/api/skills/sites/nothing")

    assert answer.status_code == 400
    assert "no site with the name" in answer.json()["detail"]


def test_the_sites_are_refused_when_the_skills_are_off(make_client, home):
    client = make_client(project_config="skills:\n  enabled: false\n")

    assert client.get("/api/skills/sites").status_code == 403
    assert client.get("/api/skills/sites/superpowers").status_code == 403


def test_the_page_gets_all_the_skills_of_a_site(make_client, home, daemon, monkeypatch):
    """The page asks for all of them and makes the pages itself."""
    daemon.push({"pdf-report": "Make a PDF report."})
    site = Site(id="test", repo="remote", path="skills", kind="gitee")
    monkeypatch.setattr(sites, "HOSTS", {"gitee": f"git://127.0.0.1:{daemon.port}"})
    monkeypatch.setattr(sites, "SITES", (site,))
    monkeypatch.setattr(skills_api, "SITES", (site,))
    client = make_client(project_config=NETWORK)

    answer = client.get("/api/skills/sites/test")

    body = answer.json()
    assert answer.status_code == 200
    assert body["total"] == 1
    assert body["page_size"] == 6
    assert [skill["name"] for skill in body["skills"]] == ["pdf-report"]
    assert body["skills"][0]["source_text"] == "gitee:remote/skills/pdf-report"


def test_a_site_is_fetched_again_when_the_page_asks_for_it(make_client, home, daemon, monkeypatch):
    """The sync button of the page throws the clone away."""
    daemon.push({"pdf-report": "Make a PDF report."})
    site = Site(id="test", repo="remote", path="skills", kind="gitee")
    monkeypatch.setattr(sites, "HOSTS", {"gitee": f"git://127.0.0.1:{daemon.port}"})
    monkeypatch.setattr(sites, "SITES", (site,))
    monkeypatch.setattr(skills_api, "SITES", (site,))
    client = make_client(project_config=NETWORK)
    client.get("/api/skills/sites/test")
    daemon.push({"pdf-report": "Make a PDF report.", "slides": "Make the slides."})

    answer = client.get("/api/skills/sites/test?refresh=true")

    assert [skill["name"] for skill in answer.json()["skills"]] == ["pdf-report", "slides"]
