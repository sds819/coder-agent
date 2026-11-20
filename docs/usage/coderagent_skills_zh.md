# 技能

技能是给某一类反复出现的任务准备的一包说明、脚本和资源。

> 英文版：[Skills](coderagent_skills.md)

```
.coderagent/skills/pdf-report/
├── SKILL.md
├── scripts/
│   └── make_report.py
└── assets/
    └── template.docx
```

`SKILL.md` 说明这个技能是干什么的。模型看到每个技能的名字和描述，描述跟任务对得上时
才把整个技能读进来：

```markdown
---
name: pdf-report
description: Make a PDF report out of a folder of notes.
---
用 `scripts/make_report.py` 生成报告：

    python scripts/make_report.py notes/ --template assets/template.docx

报告落在 `report.pdf`。
```

| 字段 | 是什么 | 默认值 |
|---|---|---|
| `name` | 技能的名字 | 目录名 |
| `description` | 干什么用的，什么时候用 | |

正文是模型加载技能时读到的指令。没有 front matter 的文件会被忽略。

## 技能在哪里找

| 位置 | 是什么 |
|---|---|
| `.coderagent/skills/*/SKILL.md` | 项目的技能 |
| `~/.coderagent/skills/*/SKILL.md` | 用户的技能 |

项目排在后面，所以项目可以用同名技能盖掉用户的。`MSWEA_CODER_HOME` 换用户目录的位置。

`/skills` 把它们列出来：

```
pdf-report       Make a PDF report out of a folder of notes.
                 /path/to/project/.coderagent/skills/pdf-report
                 from owner/repo/skills/pdf-report@v1.2.0 (sha256 9f2cabc123)
```

最后一行只有从网络装来的技能才有：它说这个技能从哪来、内容哈希是多少。

## 模型怎么用技能

技能的索引进系统提示词，所以模型知道有哪些技能可选，又不用为此花上下文：

```
<skills>
These skills are available. Load one with the `skill` tool when its description fits the task.
- pdf-report: Make a PDF report out of a folder of notes.
</skills>
```

任务对得上时，模型用名字调用 `skill` 工具。工具给出 `SKILL.md` 的正文和目录路径，模型
就知道脚本在哪儿。脚本本身用 `bash` 跑，在会话的工作目录里。

技能是一包步骤，不是一个程序：模型读指令、照着做，脚本只是让步骤省事一点。

## 从网络安装技能

网页版的 `/skills` 页（见[网页版](coderagent_web_zh.md)）列出装好的技能，也能从网络装新的。

```
coder web
```

页面分两块：**已安装**——`~/.coderagent/skills/` 里的每个技能，带来源和内容摘要；
**从网络安装**——一个填来源的输入框和一个按钮，点了就把技能下载下来给你看。
磁盘上先不写任何东西：下载的东西先在暂存区里等着，页面先摊开给你看。

### 来源

| 你写的 | 是什么 |
|---|---|
| `owner/repo` | 一个 GitHub 仓库，默认分支 |
| `owner/repo@v1.2.0` | GitHub 仓库的某个 tag、分支或提交 |
| `owner/repo/skills/pdf-report@v1` | GitHub 仓库里的一个技能 |
| `https://host/org/repo.git`、`git@host:org/repo.git` | 一个 git 仓库 |
| `https://example.com/skills/pdf-report/SKILL.md` | 一个文件 |
| `https://example.com/index.json` | 一个注册表：一份技能清单 |

地址有两种讲法时，用前缀说清你要哪个：`github:`、`git:`、`registry:`、`direct:`。

直链只有一个文件，所以这样的技能没有脚本也没有资源——这是它的代价。

注册表就是一个 JSON 文件：

```json
{
  "name": "my registry",
  "skills": [
    {
      "name": "pdf-report",
      "description": "Make a PDF report out of a folder of notes.",
      "source": { "kind": "github", "repo": "owner/repo", "path": "skills/pdf-report", "ref": "v1.2.0" }
    }
  ]
}
```

读不通的那一条被跳过，其余的照常用。`skills.registries` 里的注册表会在页面上列出来。

### 预览

下载的东西在 `~/.coderagent/cache/skills/` 里等半小时。页面给你看：

- 来源、文件个数和内容的摘要；
- 警告——带脚本的技能会被标出来，因为模型可能会跑它；
- **`SKILL.md` 的全文**，原样给你看。这是你和一个「告诉模型该做什么」的文件之间唯一的
  防线，所以要看；
- 其余文件的清单和大小。

`安装` 把它写进 `~/.coderagent/skills/<name>/`；`取消` 就扔掉。

### 会被检查的东西

| 限制 | 默认值 | 配置键 |
|---|---|---|
| 一次下载的字节数 | 8 MiB | `skills.max_bytes` |
| 单个文件的字节数 | 1 MiB | `skills.max_file_bytes` |
| 文件个数 | 2000 | `skills.max_files` |
| 目录最深几层 | 16 | `skills.max_depth` |
| 一次下载最多几秒 | 30 | `skills.timeout` |

每个文件的路径也要过一遍：越出技能目录的路径、链接、设备文件、Windows 不让用的名字——
都被拒绝，而且下载会被整个扔掉，不会装一半。

只允许 `https://`；指向内网的主机也拒绝，所以这个页面不能拿去探你网络里的机器。
git 地址需要机器上有 `git`，没有的话页面直说，不偷偷换别的方式。

### 锁文件

`~/.coderagent/skills.lock.json` 记着这里装过什么、来自哪里：

```json
{
  "version": 1,
  "skills": {
    "pdf-report": {
      "source": { "kind": "github", "repo": "owner/repo", "path": "skills/pdf-report", "ref": "v1.2.0" },
      "sha256": "9f2c…",
      "installed_at": "2026-11-20T10:00:00+00:00",
      "files": [{ "path": "SKILL.md", "size": 812, "sha256": "…" }]
    }
  }
}
```

每个文件有自己的 sha256，整个技能还有一个把它们算在一起的摘要。

**检查更新**会重新抓一次来源：摘要一样就是内容没变，不一样页面就把新的摊开给你看，
你点头才替换旧的。**卸载**删掉从网络装来的技能。自己放进去的技能是你的——页面会这么说，
然后不动它。

### 什么时候生效

**新会话里生效。** 技能的索引进系统提示词，而系统提示词是会话开始时搭的，所以正在跑的
会话还是它启动时那批技能。终端里的 `/skills` 每次现读磁盘，马上就能看到新的。

### 配置

```yaml
skills:
  enabled: true
  max_bytes: 8388608
  max_file_bytes: 1048576
  max_files: 2000
  max_depth: 16
  timeout: 30
  registries: []
  github_token: ""
  allow_insecure: false
  allowed_hosts: []
```

| 键 | 作用 |
|---|---|
| `enabled` | `false` 时页面的写操作一律拒绝。磁盘上已有的技能照样被 agent 读到——这个开关管的是「装」，不是「用」 |
| `registries` | 页面上提供的 `index.json` 地址 |
| `github_token` | GitHub 的令牌，用来绕开匿名请求的配额。它只进请求头，**不写进锁文件**——别把它放在项目文件里 |
| `allow_insecure` | `true` 才允许 `http://`。规矩是 `https://` |
| `allowed_hosts` | 可以指向内网的主机。其余的不行 |

会话的网络开关（`permissions.network`）**不**管这些下载：它管的是模型跑的命令，而下载是
你自己在页面上做的动作。

### 技能里的脚本

带脚本的技能在预览里会被标出来。模型可能用 `bash` 跑它们，那还是会话的权限层管着：
装一个技能不会给它更多权限。

## 技能和命令的区别

| | 技能 | 命令 |
|---|---|---|
| 谁调用 | 模型，描述对得上的时候 | 用户，打 `/名字` |
| 是什么 | 模型照着做的指令 | 用户发出去的一句话 |
| 留下什么 | 文件、报告、提交 | 对话里的一句话 |

命令在 `.coderagent/commands/*.md`，见[命令](coderagent_commands_zh.md)。技能在
`.coderagent/skills/<名字>/SKILL.md`。

## 权限

`skill` 工具跟 `bash` 一样是要问的工具。没有终端就没人回答，所以脚本里会被拒绝：

```bash
coder --task "..." --permission-mode bypass
```

或者自己写一条规则：

```yaml
# .coderagent/rules.yaml
rules:
  - tool: skill
    pattern: "*"
    decision: allow
```
