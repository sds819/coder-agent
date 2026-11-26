# coding agent

> 英文版：[README.md](docs/readme.md)

[![Docs](https://img.shields.io/badge/Docs-green?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://github.com/sds819/coder-agent/tree/main/docs)

`coder` 是一个交互式 coding agent：它读代码、写代码、跑命令，然后告诉你它改了什么。
它能跑在终端里，**也能**跑在浏览器里，还是一个能当库用的东西。

```bash
pip install "coder-agent @ git+https://github.com/sds819/coder-agent"
cd my-project

coder                        # 终端界面
coder web                    # 同一个 agent，跑在浏览器里
coder eval path/to/suite     # 拿一个任务集跑这个 agent
```

这个包还没发到 PyPI 上，所以从仓库里装。

## 它能做什么

**工具。** 十四个内置工具：`read`、`write`、`edit`、`multi_edit` 和 `apply_patch` 改文件；
`glob`、`grep` 和 `ls` 找代码；`bash`、`bash_output` 和 `bash_kill` 跑命令（也能放后台跑）；
`todo_write` 记任务清单；`task` 起一个子 agent；`skill` 加载技能。

**权限。** 五种模式：`default`（凡是会改动东西的都问）、`acceptEdits`（写文件直接过，其余
还是问）、`plan` 和 `readonly`（什么都不改）以及 `bypass`（什么都不问）。规则写在
`~/.coderagent/rules.yaml`（你的）和 `.coderagent/rules.yaml`（项目的）里；`deny` 永远压过
`allow`。

**会话。** 每个会话都有一份事件日志，所以它能被续接（`coder --resume`）、分叉（`/fork`）、
回退（`/rewind`）和导出（`coder export`）；会话的轨迹还能发给 OpenTelemetry 采集器。
浏览器里开的会话能在终端里接着跑，反过来也一样。

**上下文。** 对话到预算的 80% 会被压缩；摘要留着目标、发现、决定、动过的文件和还没解决的问题。
一轮结束前按顺序过三道闸门：`Stop` hook、项目的 `verify.commands`、输出 schema。

**记忆。** 项目把记忆写在 `.coderagent/memory/*.md`，你自己的偏好写在 `~/.coderagent/CLAUDE.md`，
`/init` 给仓库写一份 `AGENTS.md`。

**子 agent 和路由。** `task` 起一个子 agent（`code-explorer`、`verifier`、`refactorer`，
还有你自己写的）。不同的活可以用不同的模型：`main`、`cheap`、`strong`、`summarize`、
`reflect` 和 `review`。

**扩展。** 九个事件上的 hook（`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`Stop`、
`SessionStart`、`SessionEnd`、`SubagentStop`、`PreCompact`、`PostCompact`）、MCP server、插件、
技能和自定义 slash 命令。

**沙箱。** 命令可以跑在 `local`、`docker`、`singularity`、`bubblewrap`、`contree`
或者 SWE-ReX（`swerex_docker`、`swerex_modal`）里。

**35 个 slash 命令**（`/model`、`/mode`、`/plan`、`/review`、`/diff`、`/cost`、
`/context`、`/compact`、`/resume`、`/fork`、`/agents`、`/permissions`、`/hooks`、`/sandbox` 等）——
浏览器里是同一套。

**网页版。** `coder web` 提供聊天页、设置页（模型和权限都是表单）、文件树和这一轮改动的 diff。
每个动作都是普通 HTTP 调用，所以脚本也能驱动它；API 文档在 `/api/docs`。

**评测。** `coder eval <suite>` 拿一个任务集跑 agent，并报告每个任务的结果；
`coder eval-compare` 比对两份报告，指出哪些任务退化了。

> **警告**
>
> 网页版**没有认证**：能访问端口的人就能驱动 agent 在当前目录里跑命令，所以默认只听 `127.0.0.1`。

## 模型

模型走 [litellm](https://github.com/BerriAI/litellm)，所以 litellm 支持的模型都能用，只要带上
厂商前缀（`anthropic/…`、`deepseek/…`）。厂商的 key 从环境变量读（`ANTHROPIC_API_KEY`、
`OPENAI_API_KEY` 等），或者从 `~/.coderagent/.env` 读。

```bash
coder -m deepseek/deepseek-flash --task "修好那个失败的测试"
```

## 文档

`docs/usage` 里：

* [快速开始](docs/usage/coderagent_quickstart.md)——装上、配置模型、跑第一轮
* [功能](docs/usage/coderagent_features_zh.md)——一页看完所有功能，外加你可能撞到的报错
* [网页版](docs/usage/coderagent_web_zh.md)——聊天页、设置页、HTTP API、安全模型
* [命令](docs/usage/coderagent_commands_zh.md)——全部 slash 命令
* [子 agent](docs/usage/coderagent_subagents_zh.md)——子 agent 和模型路由
* [Hooks](docs/usage/coderagent_hooks_zh.md)——九个事件上的 hook
* [沙箱](docs/usage/coderagent_sandbox_zh.md)——命令跑在哪里
* [评测](docs/usage/coderagent_eval_zh.md)——任务集、报告和对比
* [记忆](docs/usage/coderagent_memory.md)——项目记忆和你的偏好
* [技能](docs/usage/coderagent_skills.md)——agent 能加载的技能
* [插件](docs/usage/coderagent_plugins.md)——扩展它的插件
* [MCP server](docs/usage/coderagent_mcp.md)——别的 server 带来的工具
* [会话的轨迹](docs/usage/coderagent_export.md)——导出轨迹，发给采集器

英文的文档：

* [Quick start](docs/usage/coderagent_quickstart.md)
* [Features](docs/usage/coderagent_features.md)
* [The web interface](docs/usage/coderagent_web.md)
* [Commands](docs/usage/coderagent_commands.md)
* [Sub agents](docs/usage/coderagent_subagents.md)
* [Hooks](docs/usage/coderagent_hooks.md)
* [Plugins](docs/usage/coderagent_plugins.md)
* [Sandbox](docs/usage/coderagent_sandbox.md)
* [Evals](docs/usage/coderagent_eval.md)
* [Model routing](docs/usage/coderagent_routing.md)
* [MCP servers](docs/usage/coderagent_mcp.md)
* [The trace of a session](docs/usage/coderagent_export.md)

想看它是怎么设计出来的，去 `docs/design`：

* [架构](docs/design/coding-agent-architecture.md)——层次、模块、接口、关键决定
* [设计逻辑](docs/design/coderagent-design-logic.md)——它为什么长成这样：承重的决定、不变量、取舍

## 来历

这个 agent 建立在 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) 的想法之上：
消息的线性历史、只用 `bash` 一个工具跑命令、litellm 的模型层，以及随它而来的那些沙箱环境
（Docker、Singularity、bubblewrap、contree、SWE-ReX）。其余的——agent 的循环、工具系统和权限层、
会话和事件日志、上下文引擎和它的压缩、记忆、子 agent 和模型路由、扩展（hook、MCP、插件、
技能）、终端界面、网页界面和评测工具——都是新的。

mini-swe-agent 本身是 SWE-agent 团队的研究项目。如果你觉得那部分有用，请在你的工作里引用
[SWE-agent 的论文](https://arxiv.org/abs/2405.15793)：

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```
