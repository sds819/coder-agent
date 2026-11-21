"""The skill sites on Gitee: the three that get a tab.

Gitee is where the developers in China keep their agent skills. These three
repositories are the ones worth showing: the one of Gitee itself and two
collections that hold real skills, a `SKILL.md` in every directory of them.

The skills of a site are read from a clone of its repository and not from the
API of Gitee: the API lets anonymous callers in for a while and then refuses
them, but a clone always works. The clone is kept in the cache for a while, so
the second tab is not a second wait.
"""

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from coderagent.paths import config_home
from coderagent.skills import SKILL_FILE, parse_skill
from coderagent.skills.errors import SkillError
from coderagent.skills.sandbox import Policy
from coderagent.skills.source import GITEE, clone_repository

CACHE = "cache/skills/sites"
"""Where the clones of the sites wait."""

LIFE = 12 * 60 * 60
"""The seconds a clone of a site is used before the site is fetched again."""

ROWS = 6
"""How many skills a site shows."""


@dataclass(frozen=True)
class Site:
    """A site of skills on Gitee."""

    id: str
    """The name of the site in the address of the page."""
    repo: str
    """The repository of Gitee: `owner/name`."""
    path: str = ""
    """The directory of the skills inside the repository."""

    @property
    def url(self) -> str:
        """The address of the site."""
        return f"{GITEE}/{self.repo}"


@dataclass(frozen=True)
class SiteSkill:
    """One skill of a site."""

    name: str
    description: str
    path: str
    """The directory of the skill inside the repository."""


SITES = (
    Site(id="official", repo="oschina/gitee-agent-skills", path="mcp-gitee-skills/skills"),
    Site(id="personal", repo="yang_huai_qiang1/agent-skills"),
    Site(id="tools", repo="jianchaoteng/agent-skills"),
)
"""The sites of the tabs, in the order they are shown.

The star counts of Gitee tell little: the repositories of skills are hardly
ever starred. What separates them is who keeps them and how many skills they
hold: the official one of Gitee has fourteen skills for the Gitee MCP server,
the personal collection has twelve for everyday work, the third has five for
models and deployment.
"""


def site_of(id: str) -> Site:
    """The site of an id."""
    for site in SITES:
        if site.id == id:
            return site
    raise SkillError(f"there is no site with the name {id}")


def list_skills(site: Site, policy: Policy) -> list[SiteSkill]:
    """Every skill of a site."""
    return skills_of(_checkout(site, policy), site)


def skills_of(root: Path, site: Site) -> list[SiteSkill]:
    """The skills of a clone of the repository of a site."""
    base = root / site.path if site.path else root
    if not base.is_dir():
        raise SkillError(f"there is no '{site.path}' in {site.repo}")
    skills = []
    for path in sorted(base.glob(f"*/{SKILL_FILE}")):
        skill = parse_skill(path)
        if skill is None:
            """A directory without a front matter is not a skill."""
            continue
        skills.append(
            SiteSkill(
                name=skill.name,
                description=skill.description,
                path=path.parent.relative_to(root).as_posix(),
            )
        )
    return skills


def _checkout(site: Site, policy: Policy) -> Path:
    """The clone of a site, fresh enough to be used."""
    directory = config_home() / CACHE / site.id
    if _is_fresh(directory):
        return directory
    shutil.rmtree(directory, ignore_errors=True)
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        clone_repository(f"{GITEE}/{site.repo}.git", directory, policy)
    except SkillError:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    (directory / ".fetched").write_text(str(time.time()), encoding="utf-8")
    return directory


def _is_fresh(directory: Path) -> bool:
    """Whether the clone of a site may still be used."""
    marker = directory / ".fetched"
    if not (directory / ".git").is_dir() or not marker.exists():
        return False
    try:
        return time.time() - float(marker.read_text(encoding="utf-8")) < LIFE
    except ValueError:
        return False


__all__ = [
    "CACHE",
    "LIFE",
    "ROWS",
    "SITES",
    "Site",
    "SiteSkill",
    "list_skills",
    "site_of",
    "skills_of",
]
