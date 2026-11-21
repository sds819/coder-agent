"""The sites of skills: the repositories that hold them.

The three sites below are the ones with the most stars among the repositories
that really hold skills. Their skills are read from a clone of the repository
and not from an API: the API of GitHub is quick with its quota and the API of
Gitee lets anonymous callers in for a while and then refuses them, but a clone
always works. The clone is kept in the cache for a while, so the second tab is
not a second wait.
"""

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from coderagent.paths import config_home
from coderagent.skills import SKILL_FILE, parse_skill
from coderagent.skills.errors import SkillError
from coderagent.skills.sandbox import Policy
from coderagent.skills.source import GITEE, GITHUB, clone_repository

CACHE = "cache/skills/sites"
"""Where the clones of the sites wait."""

LIFE = 12 * 60 * 60
"""The seconds a clone of a site is used before the site is fetched again."""

ROWS = 6
"""How many skills a site shows at a time."""

HOSTS = {"github": GITHUB, "gitee": GITEE}
"""Where the repositories of a kind of host are cloned from."""


@dataclass(frozen=True)
class Site:
    """A site of skills."""

    id: str
    """The name of the site in the address of the page."""

    repo: str
    """The repository of the site: `owner/name`."""

    path: str = ""
    """The directory of the skills inside the repository."""

    accent: str = "#6aa9ff"
    """The colour of the site in the page, so that the tabs differ."""

    kind: str = "github"
    """The host of the repository: `github` or `gitee`."""

    @property
    def url(self) -> str:
        """The address of the site."""
        return f"{HOSTS[self.kind]}/{self.repo}"


@dataclass(frozen=True)
class SiteSkill:
    """One skill of a site."""

    name: str
    description: str
    path: str
    """The directory of the skill inside the repository."""


SITES = (
    Site(id="superpowers", repo="obra/superpowers", path="skills", accent="#ef7059"),
    Site(id="anthropic", repo="anthropics/skills", path="skills", accent="#4fb0f5"),
    Site(id="composio", repo="ComposioHQ/awesome-claude-skills", accent="#a98bff"),
)
"""The sites of the tabs, in the order they are shown.

The star counts tell the order here: the sites of the tabs are the
repositories with the most stars that really hold skills. A repository of a
collection of links is no site: a site holds `SKILL.md` files.
"""


def site_of(id: str) -> Site:
    """The site of an id."""
    for site in SITES:
        if site.id == id:
            return site
    raise SkillError(f"there is no site with the name {id}")


def list_skills(site: Site, policy: Policy, refresh: bool = False) -> list[SiteSkill]:
    """Every skill of a site.

    With `refresh` the clone is thrown away and fetched again: the page asks
    for that when the user wants to see what the site looks like now.
    """
    return skills_of(_checkout(site, policy, refresh), site)


def skills_of(root: Path, site: Site) -> list[SiteSkill]:
    """The skills of a clone of the repository of a site.

    A skill may sit anywhere in the directory of the site: the collections
    put them into folders of their own. The directories whose name begins
    with a dot are left out: they hold the machinery of the repository, not
    skills for the agent.
    """
    base = root / site.path if site.path else root
    if not base.is_dir():
        raise SkillError(f"there is no '{site.path}' in {site.repo}")
    skills = []
    for path in sorted(base.glob(f"**/{SKILL_FILE}")):
        if any(part.startswith(".") for part in path.relative_to(base).parts[:-1]):
            continue
        skill = _parse(path)
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


def _parse(path: Path):
    """The skill of a file, when the file is one."""
    try:
        return parse_skill(path)
    except (OSError, UnicodeDecodeError):
        return None


def _checkout(site: Site, policy: Policy, refresh: bool = False) -> Path:
    """The clone of a site, fresh enough to be used."""
    directory = config_home() / CACHE / site.id
    if not refresh and _is_fresh(directory):
        return directory
    shutil.rmtree(directory, ignore_errors=True)
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        clone_repository(f"{site.url}.git", directory, policy)
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
    "HOSTS",
    "LIFE",
    "ROWS",
    "SITES",
    "Site",
    "SiteSkill",
    "list_skills",
    "site_of",
    "skills_of",
]
