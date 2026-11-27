# The coding agent

> 中文版：[README_zh.md](docs/readme_zh.md)

[![Docs](https://img.shields.io/badge/Docs-green?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://github.com/sds819/coder-agent/tree/main/docs)

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

> [!WARNING]
> The browser interface has **no authentication**: everybody who can reach the port can drive the agent and run
> shell commands in the working directory. Keep it on `127.0.0.1`.

## The model

The models go through [litellm](https://github.com/BerriAI/litellm), so every model that litellm
supports works — with the name of the provider in front of it (`anthropic/…`, `deepseek/…`). The
key of the provider is read from the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …) or
from `~/.coderagent/.env`.

```bash
coder -m deepseek/deepseek-flash --task "fix the failing test"
```

The model is configured in the terminal, in the terminal interface and in the browser. All three
write the same file, `~/.coderagent/config.yaml`:

```bash
coder model                                                   # show the settings in effect
coder model --name deepseek/deepseek-flash --max-retries 3    # write them down
coder model --test                                            # try the model out
```

The try-out and the writing are two steps: `--test` never writes anything, and the writing never
waits for the try-out — a configuration that does not work yet is worth writing down, to be fixed
later. The terminal interface has the same three steps (`/model name=… base=… key=… retries=…`,
`/model --test`, `/model --save`), and the settings page of the browser has a **Test** button next
to **Save**.

**Pictures.** When a picture is sent to a model nobody knows anything about, the agent asks it
once — with a picture of one color and the question what color it is — and writes the answer to
your own configuration file. The next time the configuration says it, and the model is never asked
again. A model that cannot take pictures is refused the turn, instead of making up an answer.

## Read more

In `docs/usage`:

* [Quick start](docs/usage/coderagent_quickstart.md) — install it, set the model, run the first round (中文)
* [Everything `coder` can do](docs/usage/coderagent_features.md) — one page, every feature, with the errors you may hit
* [The web interface](docs/usage/coderagent_web.md) — the chat page, the settings page, the HTTP API, the security model
* [The commands](docs/usage/coderagent_commands.md) — every slash command
* [Sub agents](docs/usage/coderagent_subagents.md) — sub agents and their own models
* [Hooks](docs/usage/coderagent_hooks.md) — hooks on nine events
* [The sandbox](docs/usage/coderagent_sandbox.md) — where the commands run
* [The eval harness](docs/usage/coderagent_eval.md) — task suites, reports, comparisons
* [Model routing](docs/usage/coderagent_routing.md) — which model does which job
* [Memory](docs/usage/coderagent_memory.md) — project memory and your preferences
* [Skills](docs/usage/coderagent_skills.md) — the skills the agent may load
* [Plugins](docs/usage/coderagent_plugins.md) — the plugins that extend it
* [MCP servers](docs/usage/coderagent_mcp.md) — the tools other servers bring
* [The trace of a session](docs/usage/coderagent_export.md) — export the trace, send it to a collector

And if you want to know how it was designed, see `docs/design`:

* [The architecture](docs/design/coding-agent-architecture.md) — the layers, the modules, the interfaces, the key decisions
* [The design logic](docs/design/coderagent-design-logic.md) — why it grew this way: the load-bearing decisions, the invariants, the trade-offs

<a id="chinese"></a>

### 中文

这份 README 有中文版，文档也有中文的：

* [中文版 README](docs/readme_zh.md)——整篇中文的这份介绍
* [快速开始](docs/usage/coderagent_quickstart.md)——装上、配置模型、跑第一轮
* [功能](docs/usage/coderagent_features_zh.md)——一页看完所有功能，外加你可能撞到的报错
* [网页版](docs/usage/coderagent_web_zh.md)——聊天页、设置页、HTTP API、安全模型
* [命令](docs/usage/coderagent_commands_zh.md)——全部 slash 命令
* [子 agent](docs/usage/coderagent_subagents_zh.md)——子 agent 和模型路由
* [Hooks](docs/usage/coderagent_hooks_zh.md)——九个事件上的 hook
* [沙箱](docs/usage/coderagent_sandbox_zh.md)——命令跑在哪里
* [评测](docs/usage/coderagent_eval_zh.md)——任务集、报告和对比

## Where it comes from

This agent is built on the ideas of [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent),
the minimal AI software engineering agent: the linear history of the messages, the commands run
through one `bash` tool, the model layer of litellm, and the sandbox environments (Docker,
Singularity, bubblewrap, contree, SWE-ReX) that came with it. Everything else — the agent loop,
the tool system and the permission layer, the sessions and the event log, the context engine and
its compaction, the memory, the sub agents and the model routing, the extensions (hooks, MCP,
plugins, skills), the terminal interface, the web interface and the evaluation harness — is new.

mini-swe-agent itself is a research project of the SWE-agent team. If you found that work helpful,
please consider citing the [SWE-agent paper](https://arxiv.org/abs/2405.15793) in your work:

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```
