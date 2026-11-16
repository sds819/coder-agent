"""MCP: the tools of an MCP server, used like the built-in ones."""

import json
import socket
import subprocess
import sys
import time

import pytest

from coderagent.config.schema import MCPConfig, MCPServerConfig
from coderagent.testing.factory import build_context
from coderagent.tools.mcp import MCPClient, MCPManager, tool_name

pytest.importorskip("mcp")

SERVER = """
from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    "Echo the text back."
    return f"echo: {text}"


server.run()
"""

HTTP_SERVER = """
from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    "Echo the text back."
    return f"echo: {{text}}"


server.run(transport="streamable-http", host="127.0.0.1", port={port})
"""

TWO_TOOLS = """
from mcp.server.mcpserver import MCPServer

server = MCPServer("echo")


@server.tool()
def echo(text: str) -> str:
    "Echo the text back."
    return f"echo: {text}"


@server.tool()
def shout(text: str) -> str:
    "Shout the text."
    return text.upper()


server.run()
"""

RECORDER = """
from http.server import BaseHTTPRequestHandler, HTTPServer

seen = {seen!r}


class Handler(BaseHTTPRequestHandler):
    def _record(self):
        with open(seen, "a", encoding="utf-8") as handle:
            handle.write(self.headers.get("X-Test", "") + "\\n")

    def do_POST(self):
        self._record()
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        self._record()
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", {port}), Handler).serve_forever()
"""


def _server(tmp_path) -> str:
    path = tmp_path / "server.py"
    path.write_text(SERVER, encoding="utf-8")
    return f"{sys.executable} {path}"


def _config(tmp_path, **kwargs) -> MCPServerConfig:
    return MCPServerConfig(name="echo", command=_server(tmp_path), **kwargs)


def _two_tools(tmp_path, **kwargs) -> MCPServerConfig:
    """A server with two tools: one of them may be hidden."""
    path = tmp_path / "two.py"
    path.write_text(TWO_TOOLS, encoding="utf-8")
    return MCPServerConfig(name="echo", command=f"{sys.executable} {path}", **kwargs)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for(port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise AssertionError(f"nothing listens on the port {port}")


def test_the_tools_of_the_server_are_named_after_the_server(tmp_path):
    client = MCPClient(_config(tmp_path))
    tools = client.start()
    client.stop()
    assert [tool.name for tool in tools] == ["mcp__echo__echo"]
    assert tool_name("echo", "echo") == "mcp__echo__echo"


def test_only_the_tools_that_are_allowed_are_seen(tmp_path):
    client = MCPClient(_two_tools(tmp_path, enabled_tools=["echo"]))
    tools = client.start()
    client.stop()
    assert [tool.name for tool in tools] == ["mcp__echo__echo"]


def test_a_tool_that_is_forbidden_is_not_seen(tmp_path):
    client = MCPClient(_two_tools(tmp_path, disabled_tools=["shout"]))
    tools = client.start()
    client.stop()
    assert [tool.name for tool in tools] == ["mcp__echo__echo"]


def test_a_star_means_every_tool(tmp_path):
    client = MCPClient(_two_tools(tmp_path, enabled_tools=["*"], disabled_tools=["shout"]))
    tools = client.start()
    client.stop()
    assert [tool.name for tool in tools] == ["mcp__echo__echo"]


def test_every_tool_of_the_server_can_be_hidden(tmp_path):
    client = MCPClient(_two_tools(tmp_path, disabled_tools=["*"]))
    tools = client.start()
    client.stop()
    assert tools == []


def test_the_schema_of_the_tool_is_the_one_of_the_server(tmp_path):
    client = MCPClient(_config(tmp_path))
    tools = client.start()
    client.stop()
    assert tools[0].parameters["properties"]["text"]["type"] == "string"
    assert tools[0].description == "Echo the text back."


def test_a_tool_of_the_server_can_be_called(tmp_path):
    client = MCPClient(_config(tmp_path))
    client.start()
    try:
        result = client.tools[0].run({"text": "hi"}, build_context(tmp_path))
    finally:
        client.stop()
    assert result.content == "echo: hi"
    assert not result.is_error


def test_a_broken_connection_is_tried_once_more(tmp_path):
    """The server dies on the first call; the client reconnects and the call works."""
    marker = tmp_path / "died"
    server = tmp_path / "server.py"
    server.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from mcp.server.mcpserver import MCPServer\n"
        f"marker = Path({str(marker)!r})\n"
        "server = MCPServer('echo')\n"
        "@server.tool()\n"
        "def echo(text: str) -> str:\n"
        "    'Echo the text back.'\n"
        "    if not marker.exists():\n"
        "        marker.write_text('x')\n"
        "        os._exit(1)\n"
        "    return f'echo: {text}'\n"
        "server.run()\n",
        encoding="utf-8",
    )
    client = MCPClient(MCPServerConfig(name="echo", command=f"{sys.executable} {server}"), timeout=30)
    client.start()
    try:
        result = client.call("echo", {"text": "hi"})
    finally:
        client.stop()
    assert result.content == "echo: hi"


def test_a_call_to_an_unknown_tool_fails(tmp_path):
    client = MCPClient(_config(tmp_path))
    client.start()
    try:
        result = client.call("nope", {})
    finally:
        client.stop()
    assert "nope" in result.content


def test_a_server_that_does_not_start_is_reported(tmp_path):
    client = MCPClient(MCPServerConfig(name="broken", command=f"{sys.executable} -c 'import nothing'"))
    assert client.start() == []
    assert client.error


def test_the_manager_starts_every_server(tmp_path):
    manager = MCPManager(MCPConfig(servers=[_config(tmp_path)], timeout=30))
    try:
        tools = manager.start()
        assert [tool.name for tool in tools] == ["mcp__echo__echo"]
        assert manager.status() == {"echo": "connected"}
    finally:
        manager.stop()


def test_the_tools_of_a_server_go_through_the_permission_layer(tmp_path):
    from coderagent.tools.permissions import PermissionMode, PermissionPolicy

    client = MCPClient(_config(tmp_path))
    client.start()
    try:
        tool = client.tools[0]
        policy = PermissionPolicy(PermissionMode.DEFAULT, [], cwd=tmp_path)
        assert policy.check(tool.name, {"text": "hi"}) == "ask"
        result = tool.run({"text": "hi"}, build_context(tmp_path, policy=policy))
        assert result.content == "echo: hi"
    finally:
        client.stop()


def test_the_tools_of_a_server_are_in_the_registry(tmp_path):
    from coderagent.tools.builtin import build_registry

    registry = build_registry()
    manager = MCPManager(MCPConfig(servers=[_config(tmp_path)], timeout=30))
    try:
        for tool in manager.start():
            registry.register(tool)
        assert "mcp__echo__echo" in registry.names()
        assert json.dumps(registry.schemas()).count("mcp__echo__echo") == 1
    finally:
        manager.stop()


def test_a_server_without_a_command_is_skipped(tmp_path):
    manager = MCPManager(MCPConfig(servers=[MCPServerConfig(name="empty")]))
    assert manager.start() == []
    assert manager.status() == {"empty": "no command and no url"}


def test_a_server_on_an_address_is_used(tmp_path):
    """The url of the configuration is the address of the server."""
    port = _free_port()
    server = tmp_path / "server.py"
    server.write_text(HTTP_SERVER.format(port=port), encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(server)])
    try:
        _wait_for(port)
        client = MCPClient(MCPServerConfig(name="echo", url=f"http://127.0.0.1:{port}/mcp"), timeout=30)
        client.start()
        try:
            assert [tool.name for tool in client.tools] == ["mcp__echo__echo"]
            assert client.tools[0].run({"text": "hi"}, build_context(tmp_path)).content == "echo: hi"
        finally:
            client.stop()
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_the_headers_of_the_configuration_are_sent(tmp_path):
    """The headers reach the server."""
    port = _free_port()
    seen = tmp_path / "seen.txt"
    recorder = tmp_path / "recorder.py"
    recorder.write_text(RECORDER.format(port=port, seen=str(seen)), encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(recorder)])
    try:
        _wait_for(port)
        client = MCPClient(
            MCPServerConfig(name="echo", url=f"http://127.0.0.1:{port}/mcp", headers={"X-Test": "hello"}), timeout=10
        )
        client.start()
        client.stop()
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert seen.read_text(encoding="utf-8").split() == ["hello"]


def test_a_server_with_a_command_and_an_address_is_reported(tmp_path):
    client = MCPClient(MCPServerConfig(name="echo", command="echo", url="http://127.0.0.1:1/mcp"), timeout=10)
    assert client.start() == []
    assert "both a command and a url" in client.error


def test_the_manager_can_be_used_without_the_sdk(tmp_path, monkeypatch):
    """A missing SDK must not break the agent."""
    monkeypatch.setitem(sys.modules, "mcp", None)
    client = MCPClient(_config(tmp_path))
    assert client.start() == []
    assert client.error
