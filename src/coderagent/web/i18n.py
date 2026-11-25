"""The language of the pages: Chinese for a Chinese region, English everywhere else.

The region of the visitor comes from the proxy in front of the server, or from
a geoip database. The visitor can always say which language they want: with
`?lang=zh` or with the box in the top bar, which remembers it in a cookie.

A language is added in three places: its templates in `templates/<code>/`, its
strings in `STRINGS` and its entry in `LANGUAGES`. A language that has no
templates is not offered.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coderagent.paths import config_home


@dataclass(frozen=True)
class Language:
    """A language of the pages."""

    code: str
    """The code of the language: `en`, `zh`."""

    name: str
    """The name of the language in that language: `English`, `中文`."""

    english: str
    """The name of the language in English: `English`, `Chinese`."""


LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", "English"),
    Language("zh", "中文", "Chinese"),
)
"""The languages of the pages. One is only offered when its templates are there."""

REGION_LANGUAGES = {
    "CN": "zh",
    "HK": "zh",
    "MO": "zh",
    "TW": "zh",
    "JP": "ja",
    "FR": "fr",
    "DE": "de",
}
"""The language of a region. A region whose language is not offered falls back to the browser."""

COUNTRY_HEADERS = ("CF-IPCountry", "X-AppEngine-Country", "X-Vercel-IP-Country", "X-Country-Code")
"""The headers a proxy in front of the server sets the country in."""

UNKNOWN_COUNTRIES = ("XX", "T1", "")
"""The values a proxy puts there when it does not know the country."""

GEOIP_ENV = "CODERAGENT_GEOIP_DB"
"""Where the geoip database is, if it is not in the config home."""

COOKIE = "coder_lang"
"""The cookie that holds the language the visitor chose."""

DEFAULT_LANGUAGE = "en"
"""The language of the pages when nothing else says which one."""

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "history": "earlier turns",
        "earlier_turns": "{count} earlier turns",
        "rewritten": "the agent was given: {text}",
        "tool": "tool",
        "running": "running…",
        "approval": "approval: {tool}",
        "allow": "Allow",
        "deny": "Deny",
        "always": "Always allow",
        "answered": "answered…",
        "error": "error: {message}",
        "image_bad_type": "error: that file is not an image a model takes (png, jpg, gif, webp)",
        "image_too_big": "error: the image is too big (5 MB is the limit)",
        "remove_image": "remove",
        "no_answer": "no answer: denied",
        "answered_decision": "answered: {decision}",
        "compacted": "the context was compacted ({tokens} tokens)",
        "recapped": "the conversation was summarized, nothing was dropped",
        "side_conversation": "that answer came from a conversation that goes aside",
        "verified": "the check ran, {failed} command(s) did not pass",
        "review": "the changes that are being reviewed",
        "untracked": "new files: {files}",
        "settled": "the session was settled in the memory (${cost})",
        "settled_unpriced": "the session was settled in the memory (this model has no price)",
        "rolled_back": "the conversation was rolled back to {messages} messages",
        "stop_max_turns": "the turn was cut off: it reached the ceiling of {calls} model calls",
        "stop_cost_exceeded": "the turn stopped: the budget of the session is spent",
        "stop_token_limit": "the turn stopped: the token limit of the session is reached",
        "stop_interrupted": "the turn was stopped",
        "mode_default": "Every tool that changes something asks for approval.",
        "mode_acceptEdits": "The writes go through, everything else asks for approval.",
        "mode_plan": "Read only: the agent looks around and writes down the plan.",
        "mode_readonly": "Read only: the agent looks around and answers.",
        "mode_bypass": "Nothing is asked: every tool call is allowed. For unattended runs.",
        "bypass_confirm": "Bypass mode asks nothing: every tool call goes through. Turn it on?",
        "from": "from: {source}",
        "alias_base": "the aliases file has: {base}",
        "server_mode": "The server was started with --permission-mode {mode}: the mode of the file does not decide anything.",
        "trying": "trying…",
        "ok_ms": "ok: {ms}ms",
        "saved": "saved to {path}",
        "no_key": "no key is set",
        "not_set": "not set",
        "not_an_alias": "the model is not an alias of this file, it is called as it is",
        "tools_ok": "ok, the model calls the tools",
        "tools_failed": "the model did not call the tool",
        "not_tried": "not tried",
        "row_model": "model",
        "row_api_base": "api base",
        "row_api_key": "api key",
        "row_aliases": "aliases file",
        "row_tools": "tools",
        "key_set": "set ({hint}) — click to show it",
        "key_not_set": "not set — click to show it",
        "key_of_endpoint": "the key of the endpoint",
        "field_session_id": "session id",
        "field_model": "model",
        "field_tokens": "tokens",
        "field_window": "window",
        "field_cost": "cost",
        "field_priced": "has a price",
        "field_cwd": "directory",
        "field_mode": "mode",
        "field_state": "state",
        "field_sandbox": "sandbox",
        "field_busy": "busy",
        "turns": "{count} model calls",
        "no_limit": "no limit",
        "turn_ceiling": "the configuration holds every sub agent to {count} model calls",
        "skills_none": "no skills installed yet",
        "skills_prev": "‹",
        "skills_next": "›",
        "skills_page": "page {page} of {count}",
        "skills_from": "from {source}",
        "skills_files": "{count} file(s)",
        "skills_sha256": "sha256",
        "skills_yours": "this one is yours: it was not installed from here",
        "skills_details": "Details",
        "skills_update": "Check for an update",
        "skills_uninstall": "Uninstall",
        "skills_registries": "Known registries",
        "skills_use": "Use this one",
        "skills_up_to_date": "{name} is up to date",
        "skills_removed": "{name} was removed",
        "skills_installed_ok": "{name} is installed. It takes effect in a new session.",
        "skills_uninstall_confirm": "Remove {name}?",
        "skills_downloading": "downloading…",
        "skills_site_official_name": "Gitee official",
        "skills_site_official": "The repository of Gitee itself: the skills that drive the Gitee MCP server.",
        "skills_site_personal_name": "Personal collection",
        "skills_site_personal": "A collection of everyday skills: memory, tests, the work of a developer.",
        "skills_site_tools_name": "Everyday tools",
        "skills_site_tools": "A few small ones: reading a codebase, deploying, asking a model about itself.",
        "skills_site_download": "Download",
        "skills_site_loading": "loading the site…",
        "skills_site_count": "{count} skills",
        "skills_site_sync": "Sync",
        "skills_site_syncing": "fetching the site again…",
        "skills_site_installed": "installed",
        "skills_site_empty": "this site has no skills",
        "skills_site_prev": "‹",
        "skills_site_next": "›",
        "skills_site_page": "page {page} of {count}",
    },
    "zh": {
        "history": "之前的几轮",
        "earlier_turns": "之前的 {count} 轮",
        "rewritten": "给 agent 的是：{text}",
        "tool": "工具",
        "running": "运行中…",
        "approval": "审批：{tool}",
        "allow": "允许",
        "deny": "拒绝",
        "always": "始终允许",
        "answered": "已回答…",
        "error": "错误：{message}",
        "image_bad_type": "错误：那个文件不是模型收的图片（png、jpg、gif、webp）",
        "image_too_big": "错误：图片太大了（上限 5 MB）",
        "remove_image": "移除",
        "no_answer": "没有回答：已拒绝",
        "answered_decision": "已回答：{decision}",
        "compacted": "上下文已压缩（{tokens} tokens）",
        "recapped": "对话已总结，什么都没有丢掉",
        "side_conversation": "这个回答来自一段岔开的对话",
        "verified": "校验已运行，{failed} 条命令没有通过",
        "review": "正在评审的改动",
        "untracked": "新文件：{files}",
        "settled": "会话已写入记忆（${cost}）",
        "settled_unpriced": "会话已写入记忆（这个模型没有价格）",
        "rolled_back": "对话已回滚到 {messages} 条消息",
        "stop_max_turns": "这一轮被切断了：模型调用到了上限 {calls} 次",
        "stop_cost_exceeded": "这一轮停了：会话的预算用完了",
        "stop_token_limit": "这一轮停了：会话的 token 上限到了",
        "stop_interrupted": "这一轮被停掉了",
        "mode_default": "凡是会改东西的工具都要审批。",
        "mode_acceptEdits": "写操作直接放行，其余的还是要问。",
        "mode_plan": "只读：agent 只看不改，把计划写出来。",
        "mode_readonly": "只读：agent 只看不改，把看到的说出来。",
        "mode_bypass": "一律不问，所有工具调用都放行——无人值守跑的时候用。",
        "bypass_confirm": "bypass 模式一律不问，所有工具调用都放行。要打开吗？",
        "from": "来自：{source}",
        "alias_base": "别名文件里有：{base}",
        "server_mode": "服务端是用 --permission-mode {mode} 起的：文件里的模式不作数。",
        "trying": "试试看…",
        "ok_ms": "好了：{ms} 毫秒",
        "saved": "已保存到 {path}",
        "no_key": "没有设置 key",
        "not_set": "没设置",
        "not_an_alias": "这个模型不是文件里的别名，就按原样调用",
        "tools_ok": "没问题，模型会调工具",
        "tools_failed": "模型没有调工具",
        "not_tried": "没试",
        "row_model": "模型",
        "row_api_base": "接口地址",
        "row_api_key": "key",
        "row_aliases": "别名文件",
        "row_tools": "工具",
        "key_set": "已设置（{hint}）——点一下显示",
        "key_not_set": "没设置——点一下显示",
        "key_of_endpoint": "这个地址的 key",
        "field_session_id": "会话 id",
        "field_model": "模型",
        "field_tokens": "token 数",
        "field_window": "上下文窗口",
        "field_cost": "花费",
        "field_priced": "有价格",
        "field_cwd": "目录",
        "field_mode": "模式",
        "field_state": "状态",
        "field_sandbox": "沙箱",
        "field_busy": "正忙",
        "turns": "{count} 次模型调用",
        "no_limit": "不限",
        "turn_ceiling": "配置把所有子 agent 压到 {count} 次模型调用",
        "skills_none": "还没有装任何技能",
        "skills_prev": "‹",
        "skills_next": "›",
        "skills_page": "第 {page} 页，共 {count} 页",
        "skills_from": "来自 {source}",
        "skills_files": "{count} 个文件",
        "skills_sha256": "sha256",
        "skills_yours": "这个是你自己的，不是这里装的",
        "skills_details": "详情",
        "skills_update": "检查更新",
        "skills_uninstall": "卸载",
        "skills_registries": "已知的注册表",
        "skills_use": "用它",
        "skills_up_to_date": "{name} 已经是最新的了",
        "skills_removed": "{name} 已经删掉了",
        "skills_installed_ok": "{name} 装好了，新会话里生效。",
        "skills_uninstall_confirm": "要删掉 {name} 吗？",
        "skills_downloading": "下载中…",
        "skills_site_official_name": "Gitee 官方",
        "skills_site_official": "Gitee 官方仓库：驱动 Gitee MCP 服务器的那些技能。",
        "skills_site_personal_name": "个人收藏",
        "skills_site_personal": "个人整理的合集：记忆同步、测试生成、开发流程这些日常用得上的技能。",
        "skills_site_tools_name": "日常工具",
        "skills_site_tools": "几个小而全的技能：读代码库、部署、查模型信息这类活儿。",
        "skills_site_download": "下载",
        "skills_site_loading": "正在取这个站点…",
        "skills_site_count": "{count} 个技能",
        "skills_site_sync": "同步更新",
        "skills_site_syncing": "正在重新取这个站点…",
        "skills_site_installed": "已安装",
        "skills_site_empty": "这个站点里没有技能",
        "skills_site_prev": "‹",
        "skills_site_next": "›",
        "skills_site_page": "第 {page} 页，共 {count} 页",
    },
}
"""The strings the browser shows. The templates have their own text."""


def country_of(request: Any) -> str:
    """The country of the visitor: the header of the proxy, or the geoip database."""
    for header in COUNTRY_HEADERS:
        value = request.headers.get(header, "").strip().upper()
        if value and value not in UNKNOWN_COUNTRIES:
            return value
    return _geoip_country(request.client.host if request.client else "")


_READER: Any = None
"""The geoip database, opened once."""


def _geoip_country(address: str) -> str:
    """The country of an address, with the geoip database, if there is one."""
    global _READER
    try:
        import geoip2.database
        import geoip2.errors
    except ImportError:
        return ""
    if _READER is None:
        path = Path(os.getenv(GEOIP_ENV) or config_home() / "GeoLite2-Country.mmdb")
        if not path.is_file():
            return ""
        _READER = geoip2.database.Reader(str(path))
    try:
        return _READER.country(address).country.iso_code or ""
    except geoip2.errors.AddressNotFoundError:
        return ""


def _preferred_language(header: str, available: Sequence[str]) -> str:
    """The language of the `accept-language` header, the one with the best quality."""
    best, quality = "", 0.0
    for part in header.split(","):
        name, _, parameters = part.strip().partition(";")
        weight = 1.0
        for parameter in parameters.split(";"):
            key, _, value = parameter.strip().partition("=")
            if key == "q":
                weight = float(value or 0)
        code = name.strip().lower().split("-")[0]
        if code in available and weight > quality:
            best, quality = code, weight
    return best


def _fallback(available: Sequence[str]) -> str:
    """The language of the pages when nothing else says which one."""
    if DEFAULT_LANGUAGE in available:
        return DEFAULT_LANGUAGE
    return available[0] if available else DEFAULT_LANGUAGE


def locale_of(request: Any, available: Sequence[str] = (DEFAULT_LANGUAGE,)) -> str:
    """The language of the pages.

    The choice of the visitor comes first (`?lang=` and the cookie of the
    button in the top bar), then the region of the address, then the language
    the browser asks for. A language that is not offered is ignored.
    """
    choice = request.query_params.get("lang", "").strip().lower()
    if choice in available:
        return choice
    cookie = request.cookies.get(COOKIE, "")
    if cookie in available:
        return cookie
    country = country_of(request)
    if country:
        language = REGION_LANGUAGES.get(country, "")
        return language if language in available else _fallback(available)
    return _preferred_language(request.headers.get("accept-language", ""), available) or _fallback(available)
