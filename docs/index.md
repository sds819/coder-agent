# The coding agent

`coder` is an interactive coding agent: it reads the code, writes the code, runs
the commands and tells you what it changed. It runs in the terminal **and** in
the browser, and it is a library too.

```bash
pip install "coder-agent @ git+https://github.com/sds819/coder-agent"
cd my-project

coder                        # the terminal interface
coder web                    # the same agent in the browser
coder eval path/to/suite     # run a task suite against the agent
```

The package is not on PyPI yet, so install it from the repository.

!!! info "中文"

    这份文档有中文版：[快速开始](usage/coderagent_quickstart.md)、
    [功能](usage/coderagent_features_zh.md)、[网页版](usage/coderagent_web_zh.md)。

## What it does

**Tools.** Fourteen built-ins: `read`, `write`, `edit`, `multi_edit` and `apply_patch` to change
files; `glob`, `grep` and `ls` to find code; `bash`, `bash_output` and `bash_kill` to run commands
(also in the background); `todo_write` to keep a task list; `task` to spawn a sub agent; `skill`
to load a skill.

**Permissions.** Five modes: `default` (everything that changes something asks), `acceptEdits`
(writes pass, the rest still asks), `plan` and `readonly` (nothing is changed) and `bypass`
(nothing asks). Rules live in `~/.coderagent/rules.yaml` (yours) and `.coderagent/rules.yaml`
(the project's); a `deny` always wins over an `allow`.

**Sessions.** Every session has an event log, so it can be resumed (`coder --resume`), forked
(`/fork`), rewound (`/rewind`) and exported (`coder export`). The trace of a session can be sent to
an OpenTelemetry collector. A session started in the browser can be continued in the terminal, and
the other way round.

**Context.** The conversation is compacted when it reaches 80% of the budget; the summary keeps
the goal, the findings, the decisions, the files that were touched and the open questions. Before
a round ends, three gates are checked in order: a `Stop` hook, the `verify.commands` of the
project, and the output schema.

**Memory.** The project writes `.coderagent/memory/*.md`, your own preferences live in
`~/.coderagent/CLAUDE.md`, and `/init` writes an `AGENTS.md` for the repository.

**Subagents and routing.** `task` spawns a sub agent (`code-explorer`, `verifier`, `refactorer`
and your own). Different jobs can use different models: `main`, `cheap`, `strong`, `summarize`,
`reflect` and `review`.

**Extensions.** Hooks on nine events (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`,
`SessionStart`, `SessionEnd`, `SubagentStop`, `PreCompact`, `PostCompact`), MCP servers, plugins,
skills and custom slash commands.

**Sandboxes.** The commands can run in `local`, `docker`, `singularity`, `bubblewrap`, `contree`
or SWE-ReX (`swerex_docker`, `swerex_modal`).

**35 slash commands** in the terminal (`/model`, `/mode`, `/plan`, `/review`, `/diff`, `/cost`,
`/context`, `/compact`, `/resume`, `/fork`, `/agents`, `/permissions`, `/hooks`, `/sandbox`, …)
— the same set in the browser.

**The web interface.** `coder web` serves a chat page, a settings page (model and permissions as
forms), a file tree and the diffs of the session. Every action is a plain HTTP call, so the
browser can be driven by a script too; the API docs are at `/api/docs`.

**Evaluation.** `coder eval <suite>` runs a task suite against the agent and reports what the
agent did with every task; `coder eval-compare` diffs two reports and names the regressions.

!!! warning "The browser interface has no authentication"

    Everybody who can reach the port can drive the agent and run shell commands in the working
    directory. Keep it on `127.0.0.1`.

## Continue reading:

<div class="grid cards">
  <a href="usage/coderagent_quickstart/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">launch</span>
        <span class="nav-card-title">Quick start</span>
      </div>
      <p class="nav-card-description">Install it, set the model, run the first round</p>
    </div>
  </a>

  <a href="usage/coderagent_features/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">flash_on</span>
        <span class="nav-card-title">Features</span>
      </div>
      <p class="nav-card-description">Every feature, on one page</p>
    </div>
  </a>

  <a href="usage/coderagent_web/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">public</span>
        <span class="nav-card-title">The web interface</span>
      </div>
      <p class="nav-card-description">The chat page, the settings page, the HTTP API</p>
    </div>
  </a>

  <a href="design/README/" class="nav-card-link">
    <div class="nav-card">
      <div class="nav-card-header">
        <span class="material-icons nav-card-icon">architecture</span>
        <span class="nav-card-title">The design</span>
      </div>
      <p class="nav-card-description">How it was built and why</p>
    </div>
  </a>
</div>

{% include-markdown "_footer.md" %}
