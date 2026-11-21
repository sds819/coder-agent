"""Where a skill comes from: a GitHub repository, a git URL, a registry or one file.

The user writes a source and the agent gets a directory with a `SKILL.md` in
it. Five kinds of source do that:

| Kind | What the user writes |
|---|---|
| `github` | `owner/repo`, `owner/repo@ref`, `owner/repo/skills/pdf-report@v1` |
| `gitee` | `gitee:owner/repo`, `gitee:owner/repo/skills/pdf-report` |
| `git` | `https://host/org/repo.git`, `git@host:org/repo.git` |
| `registry` | the address of a `index.json` that lists skills |
| `direct` | the address of one `SKILL.md` |

Nothing here is fetched before the address has been checked: only `https` may
be fetched, and a host that points inside the network is refused.
"""

import ipaddress
import json
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from coderagent.skills.errors import SkillError
from coderagent.skills.sandbox import CHUNK, Policy, check_path, unpack_tar

REDIRECTS = (301, 302, 303, 307, 308)
"""The answers of a server that says the file is somewhere else."""

HOPS = 3
"""How many times a download may be sent to another address."""

CLONE_TIMEOUT = 120
"""The seconds a clone may take. A repository is bigger than a file."""

GITEE = "https://gitee.com"
"""Where the repositories of Gitee are fetched from."""

GITHUB_API = "https://api.github.com"
"""Where the repositories of GitHub are fetched from."""

PRIVATE = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)
"""The addresses that are not out in the world. A download does not go there."""


@dataclass(frozen=True)
class Source:
    """Where a skill comes from."""

    kind: str
    """One of `github`, `gitee`, `git`, `registry` or `direct`."""
    url: str = ""
    """The address to fetch. Empty for a GitHub repository, which is built from `repo`."""
    repo: str = ""
    """The repository of GitHub or of Gitee: `owner/name`."""
    ref: str = ""
    """The tag, the branch or the commit of the repository."""
    path: str = ""
    """The directory of the skill inside the repository."""
    name: str = ""
    """The name of the skill, when the source names one."""

    def as_dict(self) -> dict:
        """The source as it is written into the lock file."""
        return {"kind": self.kind, "url": self.url, "repo": self.repo, "ref": self.ref, "path": self.path}

    def describe(self) -> str:
        """The source as the user would write it."""
        if self.kind in ("github", "gitee"):
            text = "/".join(part for part in (self.repo, self.path) if part)
            return f"{text}@{self.ref}" if self.ref else text
        return self.url


@dataclass(frozen=True)
class Entry:
    """One skill of a registry."""

    name: str
    description: str
    source: Source
    sha256: str = ""
    """The digest of the content, when the registry pins it."""


def parse_source(text: str) -> Source:
    """The source a user wrote. Raises when the text is not one."""
    text = text.strip()
    if not text:
        raise SkillError("there is no source")
    for prefix, kind in (
        ("github:", "github"),
        ("gitee:", "gitee"),
        ("git:", "git"),
        ("registry:", "registry"),
        ("direct:", "direct"),
    ):
        if text.lower().startswith(prefix):
            return _parse(kind, text[len(prefix) :].strip())
    if text.startswith("git@"):
        return Source(kind="git", url=text)
    if text.startswith(("http://", "https://")):
        return _parse_url(text)
    if "/" in text and " " not in text:
        return _parse_github(text)
    raise SkillError(f"'{text}' is not a source of a skill")


def source_of(data: object) -> Source:
    """The source of a registry entry or of the lock file."""
    if not isinstance(data, dict):
        raise SkillError("a source must be a mapping")
    kind = str(data.get("kind") or "")
    if not kind and data.get("repo"):
        kind = "github"
    if kind == "github":
        repo = str(data.get("repo") or "")
        if "/" not in repo:
            raise SkillError("a github source needs a repository")
        return Source(kind="github", repo=repo, ref=str(data.get("ref") or ""), path=str(data.get("path") or ""))
    if kind == "gitee":
        repo = str(data.get("repo") or "")
        if "/" not in repo:
            raise SkillError("a gitee source needs a repository")
        return Source(kind="gitee", repo=repo, ref=str(data.get("ref") or ""), path=str(data.get("path") or ""))
    if kind in ("git", "registry", "direct"):
        url = str(data.get("url") or "")
        if not url:
            raise SkillError(f"a {kind} source needs a url")
        return Source(kind=kind, url=url)
    raise SkillError(f"'{kind}' is not a kind of source")


def fetch(source: Source, workdir: Path, policy: Policy, token: str = "") -> Path:
    """The skill of a source, downloaded into the work directory.

    The answer is the directory of the skill, or the file of a `SKILL.md` that
    stands alone.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    if source.kind == "github":
        return _fetch_github(source, workdir, policy, token)
    if source.kind == "gitee":
        return _fetch_gitee(source, workdir, policy)
    if source.kind == "git":
        return _fetch_git(source, workdir, policy)
    if source.kind == "direct":
        return _fetch_direct(source, workdir, policy)
    raise SkillError(f"a {source.kind} is not a skill that can be installed")


def fetch_registry(url: str, policy: Policy) -> list[Entry]:
    """The skills a registry lists. A bad entry is left out, not the whole list."""
    try:
        data = json.loads(download(url, policy).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SkillError(f"the registry cannot be read: {error}") from None
    items = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SkillError("the registry does not list any skills")
    entries = []
    for item in items:
        entry = _entry(item)
        if entry is not None:
            entries.append(entry)
    return entries


def download(url: str, policy: Policy, headers: dict[str, str] | None = None) -> bytes:
    """The bytes of an address. Refuses what is too big or points inward."""
    current = url
    for _ in range(HOPS + 1):
        check_url(current, policy)
        try:
            response = requests.get(current, stream=True, timeout=policy.timeout, headers=headers or {})
        except requests.RequestException as error:
            raise SkillError(f"the download failed: {error}") from None
        with response:
            if response.status_code in REDIRECTS:
                location = response.headers.get("Location", "")
                if not location:
                    raise SkillError("the server sent a redirect without a place to go")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise SkillError(f"the download failed: the server said {response.status_code}")
            return _read(response, policy)
    raise SkillError("the download went through too many redirects")


def clone_repository(url: str, target: Path, policy: Policy) -> Path:
    """A clone of a repository, without its history.

    A skill is a directory of files: the commits that led to it are of no use
    to anybody, and the history of a big repository is a lot of download.
    """
    check_git_url(url, policy)
    if shutil.which("git") is None:
        raise SkillError("git is not installed, so a git URL cannot be used")
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, str(target)],
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise SkillError("the clone took too long") from None
    if result.returncode != 0:
        raise SkillError(f"the clone failed: {result.stderr.strip() or 'git said nothing'}")
    return target


def check_url(url: str, policy: Policy) -> None:
    """Whether an address may be fetched: the scheme, and where it points."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http") or (scheme == "http" and not policy.allow_insecure):
        raise SkillError(f"'{url}' may not be fetched: only https is allowed")
    host = parsed.hostname or ""
    if not host:
        raise SkillError(f"'{url}' has no host")
    check_host(host, policy.allowed_hosts)


def check_git_url(url: str, policy: Policy) -> None:
    """Whether an address may be cloned."""
    if url.startswith("git@"):
        check_host(url[4:].split(":")[0], policy.allowed_hosts)
        return
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http", "ssh", "git") or (scheme == "http" and not policy.allow_insecure):
        raise SkillError(f"'{url}' may not be cloned: only https and ssh are allowed")
    if parsed.hostname:
        check_host(parsed.hostname, policy.allowed_hosts)


def check_host(host: str, allowed_hosts: tuple[str, ...]) -> None:
    """Whether a host may be reached. A host inside the network may not."""
    if host in allowed_hosts:
        return
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise SkillError(f"the host '{host}' cannot be found") from None
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if any(ip in network for network in PRIVATE):
            raise SkillError(f"the host '{host}' is inside the network, it is not allowed")


def _parse(kind: str, text: str) -> Source:
    if kind == "github":
        return _parse_github(text)
    if kind == "gitee":
        return _parse_gitee(text)
    if not text:
        raise SkillError("there is no source")
    return Source(kind=kind, url=text)


def _parse_github(text: str) -> Source:
    reference, _, ref = text.partition("@")
    parts = [part for part in reference.split("/") if part]
    if len(parts) < 2:
        raise SkillError(f"'{text}' is not a repository: it needs an owner and a name")
    return Source(kind="github", repo="/".join(parts[:2]), path="/".join(parts[2:]), ref=ref)


def _parse_gitee(text: str) -> Source:
    """A repository of Gitee. The clone takes the branch the repository has."""
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        raise SkillError(f"'{text}' is not a repository: it needs an owner and a name")
    return Source(kind="gitee", repo="/".join(parts[:2]), path="/".join(parts[2:]))


def _parse_url(text: str) -> Source:
    parsed = urlparse(text)
    path = parsed.path.lower()
    if path.endswith(".json"):
        return Source(kind="registry", url=text)
    if path.endswith("skill.md"):
        return Source(kind="direct", url=text)
    if path.endswith(".git"):
        return Source(kind="git", url=text)
    if parsed.hostname in ("github.com", "www.github.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            ref = ""
            if len(parts) > 3 and parts[2] == "tree":
                ref, parts = parts[3], parts[:2] + parts[4:]
            return Source(kind="github", repo=f"{parts[0]}/{parts[1]}", path="/".join(parts[2:]), ref=ref)
    if parsed.hostname in ("gitee.com", "www.gitee.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            if len(parts) > 3 and parts[2] == "tree":
                parts = parts[:2] + parts[4:]
            return Source(kind="gitee", repo=f"{parts[0]}/{parts[1]}", path="/".join(parts[2:]))
    raise SkillError(f"'{text}' does not point at a skill: it is not a registry, a SKILL.md or a repository")


def _entry(item: object) -> Entry | None:
    """One entry of a registry. An entry that cannot be read is left out."""
    if not isinstance(item, dict):
        return None
    try:
        source = source_of(item.get("source"))
    except SkillError:
        return None
    return Entry(
        name=str(item.get("name") or ""),
        description=str(item.get("description") or ""),
        source=source,
        sha256=str(item.get("sha256") or ""),
    )


def _fetch_github(source: Source, workdir: Path, policy: Policy, token: str) -> Path:
    owner, _, name = source.repo.partition("/")
    if not owner or not name:
        raise SkillError(f"'{source.repo}' is not a repository: it needs an owner and a name")
    url = f"{GITHUB_API}/repos/{owner}/{name}/tarball/{source.ref or 'HEAD'}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    archive = workdir / "repo.tar.gz"
    archive.write_bytes(download(url, policy, headers))
    root = workdir / "repo"
    unpack_tar(archive, root, policy)
    target = check_path(root, source.path) if source.path else root
    if not target.is_dir():
        raise SkillError(f"there is no '{source.path}' in {source.repo}")
    return target


def _fetch_gitee(source: Source, workdir: Path, policy: Policy) -> Path:
    owner, _, name = source.repo.partition("/")
    if not owner or not name:
        raise SkillError(f"'{source.repo}' is not a repository: it needs an owner and a name")
    root = clone_repository(f"{GITEE}/{owner}/{name}.git", workdir / "repo", policy)
    target = check_path(root, source.path) if source.path else root
    if not target.is_dir():
        raise SkillError(f"there is no '{source.path}' in {source.repo}")
    return target


def _fetch_git(source: Source, workdir: Path, policy: Policy) -> Path:
    return clone_repository(source.url, workdir / "repo", policy)


def _fetch_direct(source: Source, workdir: Path, policy: Policy) -> Path:
    target = workdir / "SKILL.md"
    target.write_bytes(download(source.url, policy))
    return target


def _read(response: requests.Response, policy: Policy) -> bytes:
    """The body of a response, as long as it is not too long."""
    length = response.headers.get("Content-Length", "")
    if length.isdigit() and int(length) > policy.max_bytes:
        raise SkillError(f"the download is bigger than {policy.max_bytes} bytes")
    content = bytearray()
    for chunk in response.iter_content(CHUNK):
        content += chunk
        if len(content) > policy.max_bytes:
            raise SkillError(f"the download is bigger than {policy.max_bytes} bytes")
    return bytes(content)


__all__ = [
    "Entry",
    "GITEE",
    "HOPS",
    "PRIVATE",
    "REDIRECTS",
    "Source",
    "check_git_url",
    "check_host",
    "check_url",
    "clone_repository",
    "download",
    "fetch",
    "fetch_registry",
    "parse_source",
    "source_of",
]
