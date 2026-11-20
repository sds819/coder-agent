<div align="center">
<a href="https://mini-swe-agent.com/latest/"><img src="https://github.com/SWE-agent/mini-swe-agent/raw/main/docs/assets/mini-swe-agent-banner.svg" alt="mini-swe-agent banner" style="height: 7em"/></a>
</div>

# The minimal AI software engineering agent

> 中文版：[docs/readme_zh.md](docs/readme_zh.md)｜中文文档见[下面](#chinese)

📣 [mini-swe-agent now powers Ramp SWE-Bench](https://labs.ramp.com/swebench)<br/>
📣 [mini-swe-agent beats Claude Code and Codex on DeepSWE](https://deepswe.datacurve.ai/blog#evaluation-harness)<br/>
📣 [Run mini-swe-agent on our new & extremely challenging benchmark, ProgramBench](https://mini-swe-agent.com/latest/usage/programbench/)<br/>
📣 [New tutorial on building minimal AI agents](https://minimal-agent.com/)

[![Docs](https://img.shields.io/badge/Docs-green?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://mini-swe-agent.com/latest/)
[![Slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://join.slack.com/t/swe-bench/shared_invite/zt-36pj9bu5s-o3_yXPZbaH2wVnxnss1EkQ)
[![PyPI - Version](https://img.shields.io/pypi/v/mini-swe-agent?style=for-the-badge&logo=python&logoColor=white&labelColor=black&color=deeppink)](https://pypi.org/project/mini-swe-agent/)

> [!WARNING]
> This is **mini-swe-agent v2**. Read the [migration guide](https://mini-swe-agent.com/latest/advanced/v2_migration/). For the previous version, check out the [v1 branch](https://github.com/SWE-agent/mini-swe-agent/tree/v1).

In 2024, we built [SWE-bench](https://github.com/swe-bench/SWE-bench) & [SWE-agent](https://github.com/swe-agent/swe-agent) and helped kickstart the coding agent revolution.

We now ask: **What if our agent was 100x simpler, and still worked nearly as well?**

`mini` is

- **Widely adopted**: Used by Meta, NVIDIA, Essential AI, IBM, Nebius, Anyscale, Princeton University, Stanford University, and many more.
- **Minimal**: Just some 100 lines of python for the [agent class](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py) (and a bit more for the [environment](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py),
[model](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/models/litellm_model.py), and [run script](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/run/hello_world.py)) — no fancy dependencies!
- **Performant:** Scores >74% on the [SWE-bench verified benchmark](https://www.swebench.com/); starts much faster than Claude Code
- **Deployable:** Supports **local environments**, **docker/podman**, **singularity/apptainer**, **bublewrap**, **contree**, and more
- **Compatible:** Supports all models via **litellm**, **openrouter**, **portkey**, and more. Support for `/completion` and `/response` endpoints, interleaved thinking etc.
- Built by the Princeton & Stanford team behind [SWE-bench](https://swebench.com), [SWE-agent](https://swe-agent.com), and more
- **Tested:** [![Codecov](https://img.shields.io/codecov/c/github/swe-agent/mini-swe-agent?style=flat-square)](https://codecov.io/gh/SWE-agent/mini-swe-agent)

<details>

<summary>More motivation (for research)</summary>

[SWE-agent](https://swe-agent.com/latest/) jump-started the development of AI agents in 2024. Back then, we placed a lot of emphasis on tools and special interfaces for the agent.
However, one year later, as LMs have become more capable, a lot of this is not needed at all to build a useful agent!
In fact, the `mini` agent

- **Does not have any tools other than bash** — it doesn't even need to use the tool-calling interface of the LMs.
  This means that you can run it with literally any model. When running in sandboxed environments you also don't need to take care
  of installing a single package — all it needs is bash.
- **Has a completely linear history** — every step of the agent just appends to the messages and that's it.
  So there's no difference between the trajectory and the messages that you pass on to the LM.
  Great for debugging & fine-tuning.
- **Executes actions with `subprocess.run`** — every action is completely independent (as opposed to keeping a stateful shell session running).
  This makes it trivial to execute the actions in sandboxes (literally just switch out `subprocess.run` with `docker exec`) and to
  scale up effortlessly. Seriously, this is [a big deal](https://mini-swe-agent.com/latest/faq/#why-no-shell-session), trust me.

This makes it perfect as a baseline system and for a system that puts the language model (rather than
the agent scaffold) in the middle of our attention.
You can see the result on the [SWE-bench (bash only)](https://www.swebench.com/) leaderboard, that evaluates the performance of different LMs with `mini`.

</details>

<details>
<summary>More motivation (as a tool)</summary>

Some agents are overfitted research artifacts. Others are UI-heavy frontend monsters.

The `mini` agent wants to be a hackable tool, not a black box.

- **Simple** enough to understand at a glance
- **Convenient** enough to use in daily workflows
- **Flexible** to extend

Unlike other agents (including our own [swe-agent](https://swe-agent.com/latest/)), it is radically simpler, because it:

- **Does not have any tools other than bash** — it doesn't even need to use the tool-calling interface of the LMs.
  Instead of implementing custom tools for every specific thing the agent might want to do, the focus is fully on the LM utilizing the shell to its full potential.
  Want it to do something specific like opening a PR?
  Just tell the LM to figure it out rather than spending time to implement it in the agent.
- **Executes actions with `subprocess.run`** — every action is completely independent (as opposed to keeping a stateful shell session running).
  This is [a big deal](https://mini-swe-agent.com/latest/faq/#why-no-shell-session) for the stability of the agent, trust me.
- **Has a completely linear history** — every step of the agent just appends to the messages that are passed to the LM in the next step and that's it.
  This is great for debugging and understanding what the LM is prompted with.

</details>

<details>
<summary>Should I use SWE-agent or mini-SWE-agent?</summary>

You should consider `mini-swe-agent` your default choice.
In particular, you should use `mini-swe-agent` if

- You want a quick command line tool that works locally
- You want an agent with a very simple control flow
- You want even faster, simpler & more stable sandboxing & benchmark evaluations
- You are doing FT or RL and don't want to overfit to a specific agent scaffold

You should use `swe-agent` if

- You want to experiment with different sets of tools, each with their own interface
- You want to experiment with different history processors

What you get with both

- Excellent performance on SWE-Bench
- A trajectory browser

</details>

<table>
<tr>
<td width="50%">
<a href="https://mini-swe-agent.com/latest/usage/mini/"><strong>CLI</strong></a> (<code>mini</code>)
</td>
<td>
<a href="https://mini-swe-agent.com/latest/usage/swebench/"><strong>Batch inference</strong></a>
</td>
</tr>
<tr>
<td width="50%">

![mini](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/mini.gif?raw=true)

</td>
<td>

![swebench](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/swebench.gif?raw=true)

</td>
</tr>
<tr>
<td>
<a href="https://mini-swe-agent.com/latest/usage/inspector/"><strong>Trajectory browser</strong></a>
</td>
<td>
<a href="https://mini-swe-agent.com/latest/advanced/cookbook/"><strong>Python bindings</strong></a>
</td>
</tr>
<tr>
<td>

![inspector](https://github.com/SWE-agent/swe-agent-media/blob/main/media/mini/gif/inspector.gif?raw=true)

</td>
<td>

```python
agent = DefaultAgent(
    LitellmModel(model_name=...),
    LocalEnvironment(),
)
agent.run("Write a sudoku game")
```

</td>
</tr>
<tr>
<td width="50%">
<a href="docs/readme_zh.md"><strong>中文版 README</strong></a>
</td>
<td>
</td>
</tr>
</table>

## Let's get started!

**Option 1:** If you just want to try out the CLI (package installed in anonymous virtual environment)

```bash
pip install uv && uvx mini-swe-agent
# or
pip install pipx && pipx ensurepath && pipx run mini-swe-agent
```

**Option 2:** Install CLI & python bindings in current environment

```bash
pip install mini-swe-agent
mini  # run the CLI
```

**Option 3:** Install from source (developer setup)

```bash
git clone https://github.com/SWE-agent/mini-swe-agent.git
cd mini-swe-agent && pip install -e .
mini  # run the CLI
```

Read more in our [documentation](https://mini-swe-agent.com/latest/):

* [Quick start guide](https://mini-swe-agent.com/latest/quickstart/)
* [Using the `mini` CLI](https://mini-swe-agent.com/latest/usage/mini/)
* [Global configuration](https://mini-swe-agent.com/latest/advanced/global_configuration/)
* [Yaml configuration files](https://mini-swe-agent.com/latest/advanced/yaml_configuration/)
* [Power up with the cookbook](https://mini-swe-agent.com/latest/advanced/cookbook/)
* [FAQ](https://mini-swe-agent.com/latest/faq/)
* [Contribute!](https://mini-swe-agent.com/latest/contributing/)

## The coding agent (`coder`)

This repository also ships `coder`: an interactive coding agent that **reuses mini-swe-agent's
model and environment layer** (see [where it comes from](#where-it-comes-from) below) and adds
what a daily driver needs on top of it — a tool system with permissions, sessions you can resume
and fork, context compaction, memory, subagents, MCP servers, hooks — and it runs in the terminal
**and** in the browser.

```bash
pip install -e ".[web]"      # the browser interface needs fastapi, uvicorn and jinja2
cd my-project

coder                        # the terminal interface
coder web                    # the same agent in the browser
coder eval path/to/suite     # run a task suite against the agent
```

### What it does

**Tools.** Fourteen built-ins: `read`, `write`, `edit`, `multi_edit` and `apply_patch` to change
files; `glob`, `grep` and `ls` to find code; `bash`, `bash_output` and `bash_kill` to run commands
(also in the background); `todo_write` to keep a task list; `task` to spawn a sub agent; `skill`
to load a skill.

**Permissions.** Five modes: `default` (everything that changes something asks), `acceptEdits`
(writes pass, the rest still asks), `plan` and `readonly` (nothing is changed) and `bypass`
(nothing asks). Rules live in `~/.coderagent/rules.yaml` (yours) and `.coderagent/rules.yaml`
(the project's); a `deny` always wins over an `allow`.

**Sessions.** Every session has an event log, so it can be resumed (`coder --resume`), forked
(`/fork`), rewound (`/rewind`) and exported (`coder export`). A session started in the browser
can be continued in the terminal, and the other way round.

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

### Where it comes from

`coder` is not a separate project that happens to live next to mini-swe-agent — it is
mini-swe-agent's model and environment layer with a different front end on top. These parts are
mini-swe-agent's and are used as they are:

| From mini-swe-agent | What `coder` uses it for |
|---|---|
| `minisweagent.environments` (`local`, `docker`, `singularity`, `bubblewrap`, `contree`, SWE-ReX) | the sandboxes the commands run in |
| `minisweagent.config.get_config_from_spec` | the `key=value` config specs on the command line |
| `minisweagent.utils.serialize.recursive_merge` | merging the config layers |
| `minisweagent.models.utils.retry` and `...cache_control` | retrying a failing call, prompt caching |
| `minisweagent.exceptions.FormatError` | a model answer that cannot be parsed |

Everything else is new: the agent loop, the tool system and the permission layer, the sessions and
the event log, the context engine and its compaction, the memory, the sub agents and the model
routing, the extensions (hooks, MCP, plugins, skills), the terminal interface, the web interface
and the evaluation harness.

### Read more

In [docs/usage](docs/usage/):

* [Coding agent overview](docs/usage/coderagent.md) — installation, the terminal interface, configuration, tools, permissions
* [The web interface](docs/usage/coderagent_web.md) — the chat page, the settings page, the HTTP API, the security model
* [Everything `coder` can do](docs/usage/coderagent_features.md) — one page, every feature, with the errors you may hit

And if you want to know how it was designed, [docs/design](docs/design/):

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

## Attribution

The `coder` coding agent is built on **mini-swe-agent**, the agent in this repository: it uses
mini-swe-agent's model and environment layer, its configuration handling and its utilities
(see [where it comes from](#where-it-comes-from)). mini-swe-agent itself is a research project of
the SWE-agent team, and its own papers and releases are the reference for that half of the code.

If you found this work helpful, please consider citing the [SWE-agent paper](https://arxiv.org/abs/2405.15793) in your work:

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```

Our other projects:

<div align="center">
  <a href="https://github.com/SWE-agent/SWE-agent"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/sweagent_logo_text_below.svg" alt="SWE-agent" height="120px"></a>
   &nbsp;&nbsp;
  <a href="https://github.com/SWE-agent/SWE-ReX"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swerex_logo_text_below.svg" alt="SWE-ReX" height="120px"></a>
   &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/SWE-bench"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swebench_logo_text_below.svg" alt="SWE-bench" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/SWE-smith"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/swesmith_logo_text_below.svg" alt="SWE-smith" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/codeclash-ai/codeclash"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/codeclash_logo_text_below.svg" alt="CodeClash" height="120px"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/SWE-bench/sb-cli"><img src="https://raw.githubusercontent.com/SWE-agent/swe-agent-media/refs/heads/main/media/logos_banners/sbcli_logo_text_below.svg" alt="sb-cli" height="120px"></a>
</div>
