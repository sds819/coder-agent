"""The skill sites on Gitee: the tabs of the page and the skills under them."""

from pathlib import Path

import pytest

from coderagent.skills.errors import SkillError
from coderagent.skills.gitee import ROWS, SITES, Site, site_of, skills_of

SKILL = """---
name: {name}
description: {description}
---

Do the thing.
"""


def _site(tmp_path: Path, name: str, description: str = "Do the thing.") -> Site:
    """A site of skills on the disk, as a clone would hold it."""
    directory = tmp_path / name
    directory.mkdir()
    (directory / "SKILL.md").write_text(SKILL.format(name=name, description=description))
    return Site(id=name, repo=f"owner/{name}", path="")


def test_there_are_three_sites():
    """The page has a tab for each of them."""
    assert [site.id for site in SITES] == ["official", "personal", "tools"]
    assert all(site.repo.count("/") == 1 for site in SITES)
    assert all(site.path or site.repo for site in SITES)


def test_the_sites_are_of_gitee():
    """A site is a repository of Gitee."""
    assert all(site.url.startswith("https://gitee.com/") for site in SITES)


def test_a_site_that_is_not_there_is_refused():
    """The address of a site may name one that does not exist."""
    with pytest.raises(SkillError) as error:
        site_of("nothing")

    assert "no site with the name" in str(error.value)


def test_the_skills_of_a_site_are_read(tmp_path):
    """Every directory with a `SKILL.md` in it is a skill."""
    site = _site(tmp_path, "pdf-report", "Make a PDF report out of a folder of notes.")

    skills = skills_of(tmp_path, site)

    assert [(skill.name, skill.description) for skill in skills] == [
        ("pdf-report", "Make a PDF report out of a folder of notes.")
    ]
    assert skills[0].path == "pdf-report"


def test_a_directory_without_a_front_matter_is_not_a_skill(tmp_path):
    """A `SKILL.md` that says nothing about itself is of no use."""
    site = _site(tmp_path, "pdf-report")
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "SKILL.md").write_text("Just a text.")

    assert [skill.name for skill in skills_of(tmp_path, site)] == ["pdf-report"]


def test_the_skills_of_a_subdirectory_are_read(tmp_path):
    """The skills of a site may live in a directory of the repository."""
    site = Site(id="official", repo="owner/repo", path="skills")
    (tmp_path / "skills" / "pdf-report").mkdir(parents=True)
    (tmp_path / "skills" / "pdf-report" / "SKILL.md").write_text(
        SKILL.format(name="pdf-report", description="Make a PDF.")
    )

    skills = skills_of(tmp_path, site)

    assert [skill.path for skill in skills] == ["skills/pdf-report"]


def test_a_site_that_is_not_there_is_an_error(tmp_path):
    """A repository without the directory of the skills has nothing to show."""
    site = Site(id="official", repo="owner/repo", path="skills")

    with pytest.raises(SkillError) as error:
        skills_of(tmp_path, site)

    assert "there is no 'skills'" in str(error.value)


def test_a_site_shows_a_handful_of_skills():
    """The page shows a few rows for each site, not all of them."""
    assert ROWS == 6
