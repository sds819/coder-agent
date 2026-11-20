"""The skills of the web interface: what is installed, and what can be installed.

The page asks the server and the server asks the domain layer
(`coderagent.skills`) to fetch, to check and to install. Every endpoint is a
plain function: a download blocks, so FastAPI puts these into a thread pool
instead of holding the event loop.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from coderagent.paths import config_home
from coderagent.skills import SKILL_FILE, SKILLS_DIR, parse_skill
from coderagent.skills.errors import SkillError
from coderagent.skills.install import (
    Staged,
    check_update,
    install,
    read_lock,
    read_stage,
    stage,
    uninstall,
)
from coderagent.skills.sandbox import Policy, check_name, entries_of
from coderagent.skills.source import fetch_registry, parse_source
from coderagent.web.api import require_client
from coderagent.web.i18n import STRINGS, locale_of

router = APIRouter(prefix="/api/skills")

REASONS = {
    "there is no source": "没有填来源",
    "is not a source of a skill": "这不是一个技能的来源：{text}",
    "does not point at a skill": "这不是一个技能的来源：{text}",
    "is not a repository": "这不是一个仓库：{text}",
    "is not a skill that can be installed": "这个来源装不了：{message}",
    "may not be fetched": "这个地址不能下载：只允许 https",
    "may not be cloned": "这个地址不能克隆：只允许 https 和 ssh",
    "is inside the network": "这个地址在内网里，不允许",
    "cannot be found": "找不到这个主机",
    "the server said": "下载失败：服务器说 {detail}",
    "the download failed": "下载失败：{detail}",
    "the download is bigger than": "下载太大：超过了 {detail} 的上限",
    "the registry cannot be read": "注册表读不了：{detail}",
    "the registry does not list any skills": "这个注册表里没有技能",
    "git is not installed": "机器上没有 git，用不了 git 地址",
    "the clone failed": "克隆失败：{detail}",
    "the clone took too long": "克隆太久了",
    "there is no SKILL.md in it": "里面没有 SKILL.md",
    "there is no": "这个来源里没有：{detail}",
    "is not a plain file": "这个包里有一个不是普通文件的东西，已拒绝",
    "is not a path inside the skill": "这个包里有一个越界的路径，已拒绝",
    "points outside the skill": "这个包里有一个越界的路径，已拒绝",
    "has a name that": "这个包里有一个不能用的名字，已拒绝",
    "has more than": "这个包里的文件太多了",
    "is deeper than": "这个包里的目录太深了",
    "is bigger than": "这个包太大了",
    "the archive cannot be read": "这个包读不了：{detail}",
    "is not a name a skill can have": "{name} 不是技能能有的名字",
    "the preview is gone": "预览已经过期，请重新下载",
    "is installed already": "{name} 已经装过了",
    "it is yours": "{name} 不是这里装的，是你自己的",
    "cannot be read": "锁文件读不了：{detail}",
    "the skills are turned off in the configuration": "配置里把技能关掉了",
}
"""Why it did not work, in Chinese. The domain layer speaks English."""


class PreviewBody(BaseModel):
    source: str = ""


class InstallBody(BaseModel):
    stage_id: str = ""
    force: bool = False


class NameBody(BaseModel):
    name: str = ""


class RegistryBody(BaseModel):
    url: str = ""


def _settings(request: Request):
    """The skills section of the configuration."""
    return request.app.state.config_of().skills


def _guard(request: Request):
    """The settings of the skills, when they are turned on."""
    settings = _settings(request)
    if not settings.enabled:
        raise HTTPException(status_code=403, detail=_reason(request, "the skills are turned off in the configuration"))
    return settings


def _policy(request: Request) -> Policy:
    """The limits of a download, as the configuration says them."""
    return Policy.from_config(_settings(request))


def _language(request: Request) -> str:
    """The language of the visitor."""
    return locale_of(request, tuple(STRINGS))


def _reason(request: Request, message: str, text: str = "") -> str:
    """The reason of a failure, in the language of the visitor."""
    if _language(request) != "zh":
        return message
    name = message[1 : message.index("'", 1)] if message.startswith("'") and "'" in message[1:] else text
    for key, template in REASONS.items():
        index = message.find(key)
        if index < 0:
            continue
        detail = message[index + len(key) :].strip(" :")
        return template.format(detail=detail, text=text or detail, message=message, name=name)
    return f"操作失败：{message}"


def _bad_request(request: Request, error: SkillError, text: str = "") -> HTTPException:
    """A failure that is the fault of what the user wrote."""
    return HTTPException(status_code=400, detail=_reason(request, str(error), text))


def _preview_view(staged: Staged) -> dict[str, Any]:
    """What the page shows before the skill is installed."""
    return {
        "stage_id": staged.stage_id,
        "name": staged.name,
        "description": staged.description,
        "body": staged.body,
        "files": [{"path": entry.path, "size": entry.size, "sha256": entry.sha256} for entry in staged.files],
        "sha256": staged.sha256,
        "warnings": staged.warnings,
        "source": staged.source.as_dict(),
        "source_text": staged.source.describe(),
    }


@router.get("")
def list_skills(request: Request) -> dict[str, Any]:
    """The skills of the user, and where they came from."""
    lock = read_lock()
    directory = config_home() / SKILLS_DIR
    skills = []
    for path in sorted(directory.glob(f"*/{SKILL_FILE}")) if directory.is_dir() else []:
        skill = _parse(path)
        if skill is None:
            continue
        installed = lock.get(path.parent.name)
        skills.append(
            {
                "name": path.parent.name,
                "description": skill.description,
                "directory": str(path.parent),
                "managed": installed is not None,
                "source": installed.source.as_dict() if installed else {},
                "source_text": installed.source.describe() if installed else "",
                "sha256": installed.sha256 if installed else "",
                "installed_at": installed.installed_at if installed else "",
                "files": len(installed.files) if installed else _count_files(path.parent),
            }
        )
    return {"skills": skills, "registries": _settings(request).registries}


@router.get("/{name}")
def get_skill(name: str, request: Request) -> dict[str, Any]:
    """One skill, with the text the model would read."""
    try:
        check_name(name)
    except SkillError as error:
        raise _bad_request(request, error) from None
    directory = config_home() / SKILLS_DIR / name
    path = directory / SKILL_FILE
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"there is no skill with the name {name}")
    skill = _parse(path)
    installed = read_lock().get(name)
    return {
        "name": name,
        "description": skill.description if skill else "",
        "body": skill.body if skill else "",
        "directory": str(directory),
        "managed": installed is not None,
        "source": installed.source.as_dict() if installed else {},
        "source_text": installed.source.describe() if installed else "",
        "sha256": installed.sha256 if installed else "",
        "installed_at": installed.installed_at if installed else "",
        "files": [{"path": entry.path, "size": entry.size, "sha256": entry.sha256} for entry in entries_of(directory)],
    }


@router.post("/preview")
def preview(body: PreviewBody, request: Request, _: None = Depends(require_client)) -> dict[str, Any]:
    """Download a skill and show what it is, without installing it."""
    settings = _guard(request)
    try:
        source = parse_source(body.source)
    except SkillError as error:
        raise _bad_request(request, error, body.source) from None
    try:
        staged = stage(source, _policy(request), token=settings.github_token)
    except SkillError as error:
        raise _bad_request(request, error, body.source) from None
    return _preview_view(staged)


@router.post("/install")
def install_skill(body: InstallBody, request: Request, _: None = Depends(require_client)) -> dict[str, Any]:
    """Put a previewed skill where the agent finds it."""
    _guard(request)
    try:
        staged = read_stage(body.stage_id)
    except SkillError as error:
        raise _bad_request(request, error) from None
    try:
        installed = install(staged, force=body.force)
    except SkillError as error:
        if "is installed already" in str(error):
            reason = _reason(request, f"'{staged.name}' is installed already")
            hint = "；force=true 才能覆盖" if _language(request) == "zh" else "; force=true replaces it"
            raise HTTPException(status_code=409, detail=reason + hint) from None
        raise _bad_request(request, error) from None
    return {"ok": True, "name": installed.name, "sha256": installed.sha256}


@router.delete("/{name}")
def uninstall_skill(name: str, request: Request, _: None = Depends(require_client)) -> dict[str, Any]:
    """Remove a skill that was installed here."""
    _guard(request)
    try:
        check_name(name)
        uninstall(name)
    except SkillError as error:
        if "it is yours" in str(error):
            raise HTTPException(status_code=403, detail=_reason(request, str(error))) from None
        raise _bad_request(request, error) from None
    return {"ok": True, "name": name}


@router.post("/update")
def update_skill(body: NameBody, request: Request, _: None = Depends(require_client)) -> dict[str, Any]:
    """Fetch the source of a skill again and see whether it changed."""
    settings = _guard(request)
    installed = read_lock().get(body.name)
    if installed is None:
        raise HTTPException(
            status_code=400, detail=_reason(request, f"'{body.name}' was not installed here, it is yours")
        )
    try:
        staged = check_update(installed, _policy(request), token=settings.github_token)
    except SkillError as error:
        raise _bad_request(request, error) from None
    if staged is None:
        return {"ok": True, "up_to_date": True, "name": body.name}
    return {"ok": True, "up_to_date": False, "preview": _preview_view(staged)}


@router.post("/registry")
def registry(body: RegistryBody, request: Request, _: None = Depends(require_client)) -> dict[str, Any]:
    """The skills a registry lists."""
    _guard(request)
    try:
        entries = fetch_registry(body.url, _policy(request))
    except SkillError as error:
        raise _bad_request(request, error, body.url) from None
    return {
        "skills": [
            {
                "name": entry.name,
                "description": entry.description,
                "source": entry.source.as_dict(),
                "source_text": entry.source.describe(),
            }
            for entry in entries
        ]
    }


def _count_files(directory: Path) -> int:
    """How many files a skill of the user has."""
    return sum(1 for path in directory.rglob("*") if path.is_file() and not path.is_symlink())


def _parse(path: Path):
    """The skill of a file, when the file is one."""
    try:
        return parse_skill(path)
    except (OSError, UnicodeDecodeError):
        return None


__all__ = ["router"]
