<div align="center">
<a href="https://mini-swe-agent.com/latest/"><img src="https://github.com/SWE-agent/mini-swe-agent/raw/main/docs/assets/mini-swe-agent-banner.svg" alt="mini-swe-agent banner" style="height: 7em"/></a>
</div>

# 极简的 AI 软件工程 agent

> 英文版：[README.md](docs/readme.md)

📣 [mini-swe-agent 现在支撑着 Ramp SWE-Bench](https://labs.ramp.com/swebench)<br/>
📣 [mini-swe-agent 在 DeepSWE 上胜过 Claude Code 和 Codex](https://deepswe.datacurve.ai/blog#evaluation-harness)<br/>
📣 [在新而极难的基准 ProgramBench 上跑 mini-swe-agent](https://mini-swe-agent.com/latest/usage/programbench/)<br/>
📣 [写极简 AI agent 的新教程](https://minimal-agent.com/)

[![Docs](https://img.shields.io/badge/Docs-green?style=for-the-badge&logo=materialformkdocs&logoColor=white)](https://mini-swe-agent.com/latest/)
[![Slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://join.slack.com/t/swe-bench/shared_invite/zt-36pj9bu5s-o3_yXPZbaH2wVnxnss1EkQ)
[![PyPI - Version](https://img.shields.io/pypi/v/mini-swe-agent?style=for-the-badge&logo=python&logoColor=white&labelColor=black&color=deeppink)](https://pypi.org/project/mini-swe-agent/)

> **警告**
>
> 这是 **mini-swe-agent v2**。请读[迁移指南](https://mini-swe-agent.com/latest/advanced/v2_migration/)。要旧版本的话，看 [v1 分支](https://github.com/SWE-agent/mini-swe-agent/tree/v1)。

2024 年，我们做了 [SWE-bench](https://github.com/swe-bench/SWE-bench) 和 [SWE-agent](https://github.com/swe-agent/swe-agent)，帮着点燃了 coding agent 这场革命。

现在我们要问：**如果我们的 agent 简单 100 倍，效果却几乎一样好呢？**

`mini` 是

- **用得广**：Meta、NVIDIA、Essential AI、IBM、Nebius、Anyscale、普林斯顿大学、斯坦福大学都在用。
- **极简**：[agent 类](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py)只有大约 100 行 python
  （[环境](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py)、
  [模型](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/models/litellm_model.py) 和
  [运行脚本](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/run/hello_world.py) 各多一点点）——没有花哨的依赖！
- **能打**：[SWE-bench verified 基准](https://www.swebench.com/)上分数 >74%；启动比 Claude Code 快得多
- **能部署**：支持**本地环境**、**docker/podman**、**singularity/apptainer**、**bubblewrap**、**contree**，还有更多
- **兼容**：通过 **litellm**、**openrouter**、**portkey** 支持所有模型。支持 `/completion` 和 `/response` 端点、交错思考等
- 出自 [SWE-bench](https://swebench.com)、[SWE-agent](https://swe-agent.com) 背后的普林斯顿与斯坦福团队
- **测过**：[![Codecov](https://img.shields.io/codecov/c/github/swe-agent/mini-swe-agent?style=flat-square)](https://codecov.io/gh/SWE-agent/mini-swe-agent)

<details>

<summary>更多的动机（面向研究）</summary>

[SWE-agent](https://swe-agent.com/latest/) 在 2024 年点燃了 AI agent 的开发。那时候我们很看重给 agent 配工具和专用接口。
但一年之后，随着模型变强，这里面的很多东西根本不需要了，照样能做出一个有用的 agent！
实际上 `mini` agent

- **除了 bash 没有别的工具**——它甚至不需要用上模型的 tool-calling 接口。
  这意味着任何模型都能跑它。在沙箱里跑的时候，你也不用装任何包——它只要 bash 就够了。
- **历史完全线性**——agent 的每一步只是往消息列表里追加一句，完事。
  所以轨迹和你传给模型的消息没有区别。调试和微调都方便。
- **用 `subprocess.run` 执行动作**——每个动作都是完全独立的（而不是维持一个有状态的 shell 会话）。
  这让在沙箱里执行动作变得毫无负担（把 `subprocess.run` 换成 `docker exec` 就行），扩展起来也不费劲。
  说真的，这[是件大事](https://mini-swe-agent.com/latest/faq/#why-no-shell-session)，信我。

这让它非常适合当基线系统，也适合当那种把语言模型（而不是 agent 脚手架）放在注意力中心的位置。
你可以在 [SWE-bench（只用 bash）](https://www.swebench.com/) 排行榜上看到结果——那个榜就是用 `mini` 评测不同模型的。

</details>

<details>
<summary>更多的动机（当成工具用）</summary>

有些 agent 是过拟合的研究产物，有些是界面很重的前端怪物。

`mini` agent 想当一个可以随手改的工具，不是一个黑盒。

- **简单**，一眼就能看懂
- **顺手**，日常流程里用得舒服
- **灵活**，容易扩展

和别的 agent（包括我们自己的 [swe-agent](https://swe-agent.com/latest/)）不同，它简单得多，因为它：

- **除了 bash 没有别的工具**——它甚至不需要用上模型的 tool-calling 接口。
  与其给 agent 可能想做的每件具体事都实现一个专用工具，重心完全放在让模型充分发挥 shell 的能力上。
  想让它做某件具体的事，比如开一个 PR？
  直接告诉模型让它自己想办法，而不是在 agent 里花时间实现。
- **用 `subprocess.run` 执行动作**——每个动作都是完全独立的（而不是维持一个有状态的 shell 会话）。
  对 agent 的稳定性来说这[是件大事](https://mini-swe-agent.com/latest/faq/#why-no-shell-session)，信我。
- **历史完全线性**——agent 的每一步只是往传给模型的消息里追加一句，完事。
  这对调试和理解模型被喂了什么，非常有用。

</details>

<details>
<summary>我该用 SWE-agent 还是 mini-SWE-agent？</summary>

你应该默认选 `mini-swe-agent`。具体来说，下面这些情况选它：

- 你想要一个能在本地跑起来的命令行工具
- 你想要一个控制流极简的 agent
- 你想要更快、更简单、更稳的沙箱和基准评测
- 你在做微调或强化学习，不想过拟合到某个特定的 agent 脚手架

下面这些情况选 `swe-agent`：

- 你想试验不同的工具集合，每个工具有自己的接口
- 你想试验不同的历史处理器

两者都能给你

- SWE-Bench 上的好成绩
- 一个轨迹浏览器

</details>

<table>
<tr>
<td width="50%">
<a href="https://mini-swe-agent.com/latest/usage/mini/"><strong>命令行</strong></a>（<code>mini</code>）
</td>
<td>
<a href="https://mini-swe-agent.com/latest/usage/swebench/"><strong>批量推理</strong></a>
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
<a href="https://mini-swe-agent.com/latest/usage/inspector/"><strong>轨迹浏览器</strong></a>
</td>
<td>
<a href="https://mini-swe-agent.com/latest/advanced/cookbook/"><strong>Python 绑定</strong></a>
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
<a href="https://github.com/sds819/mini-swe-agent/blob/main/README.md"><strong>English README</strong></a>
</td>
<td>
</td>
</tr>
</table>

## 开始用吧！

**方式 1：** 只想试试命令行（在匿名虚拟环境里装这个包）

```bash
pip install uv && uvx mini-swe-agent
# 或者
pip install pipx && pipx ensurepath && pipx run mini-swe-agent
```

**方式 2：** 在当前环境里装命令行和 python 绑定

```bash
pip install mini-swe-agent
mini  # 跑命令行
```

**方式 3：** 从源码装（开发者的装法）

```bash
git clone https://github.com/SWE-agent/mini-swe-agent.git
cd mini-swe-agent && pip install -e .
mini  # 跑命令行
```

我们的[文档](https://mini-swe-agent.com/latest/)里还有更多：

* [快速开始](https://mini-swe-agent.com/latest/quickstart/)
* [用 `mini` 命令行](https://mini-swe-agent.com/latest/usage/mini/)
* [全局配置](https://mini-swe-agent.com/latest/advanced/global_configuration/)
* [Yaml 配置文件](https://mini-swe-agent.com/latest/advanced/yaml_configuration/)
* [用 cookbook 增强它](https://mini-swe-agent.com/latest/advanced/cookbook/)
* [常见问题](https://mini-swe-agent.com/latest/faq/)
* [来贡献！](https://mini-swe-agent.com/latest/contributing/)

## Coding agent（`coder`）

这个仓库还带着 `coder`：一个交互式 coding agent，它**复用 mini-swe-agent 的模型层和环境层**
（见下面的[它从哪儿来](#where-it-comes-from)），在上面加了日常驱动真正需要的东西——
带权限的工具系统、能续接和分叉的会话、上下文压缩、记忆、子 agent、MCP server、hooks——
而且它既能在**终端**里跑，也能在**浏览器**里跑。

```bash
pip install -e ".[web]"      # 网页版需要 fastapi、uvicorn 和 jinja2
cd my-project

coder                        # 终端界面
coder web                    # 同一个 agent，跑在浏览器里
coder eval path/to/suite     # 拿一个任务集跑这个 agent
```

### 它能做什么

**工具。** 十四个内置工具：`read`、`write`、`edit`、`multi_edit` 和 `apply_patch` 用来改文件；
`glob`、`grep` 和 `ls` 用来找代码；`bash`、`bash_output` 和 `bash_kill` 用来跑命令（也能放到后台跑）；
`todo_write` 用来记任务清单；`task` 用来开子 agent；`skill` 用来加载技能。

**权限。** 五种模式：`default`（凡是会改东西的都问）、`acceptEdits`（写操作直接放行，其余的还是要问）、
`plan` 和 `readonly`（什么都不改）以及 `bypass`（什么都不问）。规则写在 `~/.coderagent/rules.yaml`（你的）
和 `.coderagent/rules.yaml`（项目的）里；**deny 永远压过 allow**。

**会话。** 每个会话都有一份事件日志，所以它能被续接（`coder --resume`）、分叉（`/fork`）、
回退（`/rewind`）和导出（`coder export`）。浏览器里开的会话能在终端里接着聊，反过来也一样。

**上下文。** 对话占满预算的 80% 时会被压缩；摘要里留着目标、发现、决定、动过的文件和还没解决的问题。
一轮结束前三道闸门按这个顺序过：`Stop` hook、项目的 `verify.commands`、输出格式。

**记忆。** 项目把记忆写在 `.coderagent/memory/*.md`，你自己的偏好写在 `~/.coderagent/CLAUDE.md`，
`/init` 会给仓库写一份 `AGENTS.md`。

**子 agent 和路由。** `task` 用来开子 agent（`code-explorer`、`verifier`、`refactorer`，也可以是你自己的）。
不同的活可以用不同的模型：`main`、`cheap`、`strong`、`summarize`、`reflect` 和 `review`。

**扩展。** 九个事件上的 hook（`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`Stop`、
`SessionStart`、`SessionEnd`、`SubagentStop`、`PreCompact`、`PostCompact`）、MCP server、插件、
技能和自定义 slash 命令。

**沙箱。** 命令可以跑在 `local`、`docker`、`singularity`、`bubblewrap`、`contree`
或 SWE-ReX（`swerex_docker`、`swerex_modal`）里。

**35 条 slash 命令**，终端里有（`/model`、`/mode`、`/plan`、`/review`、`/diff`、`/cost`、
`/context`、`/compact`、`/resume`、`/fork`、`/agents`、`/permissions`、`/hooks`、`/sandbox`……），
浏览器里是同一套。

**网页版。** `coder web` 提供聊天页、设置页（模型和权限都是表单）、文件树和这一轮改动的 diff。
每个动作都是普通的 HTTP 调用，所以浏览器也能被脚本驱动；API 文档在 `/api/docs`。

**评测。** `coder eval <suite>` 拿一个任务集跑 agent，并报告每个任务的结果；
`coder eval-compare` 比对两份报告，指出哪些任务退化了。

> **警告**
>
> 网页版**没有认证**：能访问这个端口的人就能驱动 agent，在工作目录里跑 shell 命令。
> 把它留在 `127.0.0.1` 上。

<a id="where-it-comes-from"></a>

### 它从哪儿来

`coder` 不是碰巧住在 mini-swe-agent 旁边的另一个项目——它就是 mini-swe-agent 的模型层和环境层，
上面换了另一个前端。下面这些部分是 mini-swe-agent 的，原样拿来用：

| 来自 mini-swe-agent | `coder` 拿它做什么 |
|---|---|
| `minisweagent.environments`（`local`、`docker`、`singularity`、`bubblewrap`、`contree`、SWE-ReX） | 命令跑在哪种沙箱里 |
| `minisweagent.config.get_config_from_spec` | 命令行上的 `key=value` 配置 |
| `minisweagent.utils.serialize.recursive_merge` | 合并各层配置 |
| `minisweagent.models.utils.retry` 和 `...cache_control` | 重试失败的调用、提示词缓存 |
| `minisweagent.exceptions.FormatError` | 模型回答解析不出来 |

其余都是新写的：agent 主循环、工具系统和权限层、会话和事件日志、上下文引擎和它的压缩、记忆、
子 agent 和模型路由、扩展（hooks、MCP、插件、技能）、终端界面、网页版和评测工具。

### 再读点别的

中文文档在 `docs/usage` 里：

* [快速开始](docs/usage/coderagent_quickstart.md)——装上、配置模型、跑第一轮
* [功能](docs/usage/coderagent_features_zh.md)——一页看完所有功能，外加你可能撞到的报错
* [网页版](docs/usage/coderagent_web_zh.md)——聊天页、设置页、HTTP API、安全模型
* [命令](docs/usage/coderagent_commands_zh.md)——全部 slash 命令
* [子 agent](docs/usage/coderagent_subagents_zh.md)——子 agent 和模型路由
* [Hooks](docs/usage/coderagent_hooks_zh.md)——九个事件上的 hook
* [沙箱](docs/usage/coderagent_sandbox_zh.md)——命令跑在哪里
* [评测](docs/usage/coderagent_eval_zh.md)——任务集、报告和对比
* [English README](docs/readme.md)——英文版的那份介绍

英文的概览在 [The coding agent](docs/usage/coderagent.md)。

想知道它是怎么设计的，看 `docs/design`（英文）：

* [架构](docs/design/coding-agent-architecture.md)——分层、模块、接口、关键决定
* [设计逻辑](docs/design/coderagent-design-logic.md)——它为什么长成这样：承重的决定、不变量、取舍

## 致谢

`coder` 这个 coding agent 建立在**本仓库里的 mini-swe-agent** 之上：它用了 mini-swe-agent 的模型层和环境层、
它的配置处理和它的工具库（见[它从哪儿来](#where-it-comes-from)）。mini-swe-agent 本身是 SWE-agent 团队的
研究项目，那一半代码的参考就是它自己的论文和发布。

如果这个工作对你有帮助，欢迎在成果里引用 [SWE-agent 论文](https://arxiv.org/abs/2405.15793)：

```bibtex
@inproceedings{yang2024sweagent,
  title={{SWE}-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  author={John Yang and Carlos E Jimenez and Alexander Wettig and Kilian Lieret and Shunyu Yao and Karthik R Narasimhan and Ofir Press},
  booktitle={The Thirty-eighth Annual Conference on Neural Information Processing Systems},
  year={2024},
  url={https://arxiv.org/abs/2405.15793}
}
```

我们的其它项目：

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
