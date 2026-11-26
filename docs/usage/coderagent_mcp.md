# MCP servers

The coding agent can use the tools of an [MCP](https://modelcontextprotocol.io)
server. The MCP SDK is optional:

```bash
pip install "coder-agent[mcp] @ git+https://github.com/sds819/coder-agent"
```

## The configuration

```yaml
mcp:
  timeout: 30
  servers:
    - name: filesystem
      command: npx -y @modelcontextprotocol/server-filesystem /path/to/the/project
      env:
        LOG_LEVEL: info
```

The servers are read from the project file `.coderagent/config.yaml` and from
the user file `~/.coderagent/config.yaml`. The two lists are not added
together: the list of the user replaces the list of the project.

A server of the **project** runs code without asking the user, so it waits for
a decision first: cloning a repository must not be enough to start a program.
The servers of the **user** are the user's own, so they are used as they are.
See [The code of a project](coderagent.md#the-code-of-a-project).

| Key | What it is |
|---|---|
| `name` | The name of the server. It is part of the name of its tools |
| `command` | The command that starts the server, over the standard input and output |
| `env` | The environment of the server |
| `enabled` | `false` skips the server |
| `url` | The address of the server, for the http transport |
| `headers` | The headers of the http transport |
| `enabled_tools` | The tools of this server the agent may call. Empty means: all of them |
| `disabled_tools` | The tools of this server the agent may not call |
| `startup_timeout` | The seconds this server may take to start. Zero means: the timeout of `mcp` |
| `tool_timeout` | The seconds one call of this server may take. Zero means: the timeout of `mcp` |
| `supports_parallel_tool_calls` | Whether two calls of this server may run at the same time. `true` by default |

The `timeout` is not a key of a server: it belongs to `mcp`, next to
`servers`, and it is how long the agent waits for a server.

A server has either a `command` or a `url`, not both. With a `command` the
server is started over the standard input and output; with a `url` the agent
talks to it over http (the streamable http transport), and the `headers` go
with every request:

```yaml
mcp:
  servers:
    - name: remote
      url: https://mcp.example.com/mcp
      headers:
        Authorization: Bearer the-token-of-the-user
```

A server on this machine is not asked through the proxy of the system: the
proxy is there for the other hosts.

The `env` of a server is **added** to the environment it inherits, it does not
replace it: the server keeps `PATH`, `HOME` and the rest of the variables the
MCP SDK passes on, and the ones of the configuration win over them.

```yaml
mcp:
  servers:
    - name: filesystem
      command: npx -y @modelcontextprotocol/server-filesystem .
      env:
        LOG_LEVEL: info
```

## What the tools look like

The tools of a server are named `mcp__<server>__<tool>`, so they never clash
with the built-in tools. The schema of the tool is the schema of the server.

```
mcp__filesystem__read_file
mcp__filesystem__list_directory
```

The tools of a server are external code, so they go through the permission
layer like every other tool: in the default mode the user has to approve them.
A rule that allows one for good looks like this:

```yaml
# .coderagent/rules.yaml
rules:
  - tool: "mcp__filesystem__read_file"
    pattern: "*"
    decision: allow
```

The name of the tool is the whole name, with the server in it. The `pattern`
is `*` or the same name: a glob does not work here.

## Picking the tools of a server

A server often has more tools than the task needs. `enabled_tools` and
`disabled_tools` choose which of them the agent sees:

```yaml
mcp:
  servers:
    - name: filesystem
      command: npx -y @modelcontextprotocol/server-filesystem .
      enabled_tools: ["read_file", "list_directory"]
    - name: database
      command: npx -y @modelcontextprotocol/server-postgres
      disabled_tools: ["drop_table"]
```

The tools that are not on the list are **not in the list of tools at all**: the
model does not see them, so it cannot ask for them. The names are the names of
the server, without the `mcp__<server>__` in front of them.

`enabled_tools` comes first, `disabled_tools` after it, and both only take
tools away:

- `enabled_tools` empty: every tool of the server is there.
- `enabled_tools` with names: only those tools are there.
- `disabled_tools` with names: those tools are never there.
- `*` in `enabled_tools`: every tool of the server is there.
- `*` in `disabled_tools`: no tool of the server is there.

A name that the server does not have hides nothing, so the log says so:

```
The MCP server 'database' has no tool 'drop_table'. The name is ignored.
```

## The timeouts of a server

`mcp.timeout` is the timeout of every server. A server that needs more time
says so itself, and one server cannot hold up the others:

```yaml
mcp:
  timeout: 30
  servers:
    - name: quick
      command: npx -y @modelcontextprotocol/server-filesystem .
      startup_timeout: 5
      tool_timeout: 10
    - name: slow
      command: npx -y @modelcontextprotocol/server-database
      startup_timeout: 60
      tool_timeout: 300
```

`startup_timeout` is how long the server may take to come up, `tool_timeout` how
long one call may take. A call that takes longer fails with an error, and the
model gets the error instead of a turn that never ends.

Both are seconds. Zero — the default — means the timeout of `mcp`.

## Two calls of one server

The agent may call two tools of the same server at the same time, when the model
asks for both in one turn. A server that cannot take two calls at once says so
with `supports_parallel_tool_calls: false`, and its calls wait for each other:

```yaml
mcp:
  servers:
    - name: database
      command: npx -y @modelcontextprotocol/server-postgres
      supports_parallel_tool_calls: false
```

The flag belongs to the server, not to the session: the calls of one server wait
for each other, the calls of the other servers do not.

## The servers and the session

The servers are started when the session starts, one thread each. A server
that does not start is skipped, the reason is in the log and `/mcp` shows it.
The other servers keep working.

```
/mcp
```

```
filesystem       connected
remote           connected
broken           failed: MCPError: Connection closed
empty            no command and no url
```

`failed` is a server that was started and did not come up. `no command and no
url` is a server that says nothing about how it should be reached — it is
skipped, and it says so instead of being silent.

When a call breaks the connection, the agent reconnects and tries the call one
more time. When it fails again, the error goes back to the model.
