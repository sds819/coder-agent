"""The try-out of the model: does it answer, does it call the tools.

The try-out never writes anything: it says whether the settings work, and the
writing is a step of its own. A configuration that does not work yet is worth
writing down, to be fixed later.
"""

import time
from typing import Any

import yaml

from coderagent.models.litellm_config import locate
from coderagent.models.provider import env_var
from coderagent.models.settings import hint, key_of, key_source, key_text, provider_of


def check_litellm_config(path: str, name: str = "") -> dict[str, Any]:
    """The file of the aliases: does it exist, does it parse, what is in it."""
    if not path:
        return {"ok": True, "path": "", "aliases": [], "error": ""}
    file = locate(path)
    if not file.is_file():
        return {"ok": False, "path": str(file), "aliases": [], "error": "the file does not exist"}
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        return {"ok": False, "path": str(file), "aliases": [], "error": f"the file is not valid YAML: {error}"}
    if not isinstance(data, dict) or not isinstance(data.get("model_list"), list):
        return {"ok": False, "path": str(file), "aliases": [], "error": "the file has no model_list"}
    aliases = [
        entry.get("model_name") for entry in data["model_list"] if isinstance(entry, dict) and entry.get("model_name")
    ]
    if name and name not in aliases:
        return {
            "ok": False,
            "path": str(file),
            "aliases": aliases,
            "error": f"'{name}' is not one of the aliases of this file",
        }
    return {"ok": True, "path": str(file), "aliases": aliases, "error": ""}


def check_tools(backend) -> dict[str, Any]:
    """The model has to call the tools, or the agent cannot work at all."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Answer with a ping.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    try:
        message = backend.query([{"role": "user", "content": "Call the ping tool."}], tools=tools, max_tokens=64)
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    calls = message.get("tool_calls") or []
    return {
        "ok": bool(calls),
        "error": "" if calls else "the model did not call the tool",
        "calls": len(calls),
    }


def test_connection(effective: dict) -> dict[str, Any]:
    """See whether the settings work: the file, the call and the tools."""
    from coderagent.models.backends import LiteLLMBackend

    name = effective["model_name"]
    kwargs = effective["model_kwargs"]
    base = str(kwargs.get("api_base") or "")
    provider = effective.get("provider") or provider_of(name, base)
    key = key_of(effective)
    """The key of the environment counts too: the call below uses it."""
    report: dict[str, Any] = {
        "ok": False,
        "resolved": {
            "model_name": name,
            "provider": provider,
            "alias": effective.get("alias", ""),
            "api_base": base,
            "api_key_set": bool(key),
            "api_key_hint": hint(key),
            "key_source": key_source(str(kwargs.get("api_key") or ""), provider),
            "key_env": env_var(provider),
        },
        "file": check_litellm_config(effective.get("litellm_config", ""), effective.get("requested", "")),
    }
    """A wrong key should fail right away, not after ten tries."""
    started = time.time()
    try:
        backend = LiteLLMBackend(
            name,
            model_kwargs=kwargs,
            reasoning_effort=effective.get("reasoning_effort", ""),
            max_retries=1,
        )
        message = backend.query([{"role": "user", "content": "ping"}], max_tokens=1)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        return report
    extra = message.get("extra") or {}
    report.update(
        {
            "ok": True,
            "content": str(message.get("content", ""))[:200],
            "cost": float(extra.get("cost") or 0.0),
            "latency_ms": int((time.time() - started) * 1000),
            "tools": check_tools(backend),
        }
    )
    return report


def report_text(report: dict) -> str:
    """The report of a try-out, as the terminal and the interface show it."""
    resolved = report.get("resolved") or {}
    lines = [
        f"model: {resolved.get('model_name', '')}",
        f"provider: {resolved.get('provider', '') or '(none)'}",
        f"api base: {resolved.get('api_base', '') or '(none)'}",
        f"api key: {key_text(resolved)}",
    ]
    if report.get("error"):
        lines.append(f"error: {report['error']}")
        return "\n".join(lines)
    lines.append(f"latency: {report.get('latency_ms', 0)} ms")
    lines.append(f"cost: {report.get('cost', 0.0):.6f}")
    tools = report.get("tools") or {}
    lines.append(
        "tools: the model calls the tools" if tools.get("ok") else f"tools: {tools.get('error', 'not checked')}"
    )
    aliases = report.get("file") or {}
    if not aliases.get("ok", True):
        lines.append(f"aliases file: {aliases.get('error', '')}")
    return "\n".join(lines)
