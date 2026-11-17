# 命令

`coder` 命令起一个交互式会话。以斜杠开头的是命令，其余都是给 agent 的消息。

```bash
coder                 # 终端界面
coder --task "把失败的测试修好"   # 跑一轮，然后是答案
coder --task "/help"  # 不进界面，直接跑一个命令
```

> 英文版：[The commands of the coding agent](coderagent_commands.md)

## 在终端界面里

命令也是对话的一部分：你敲的那一行会作为你的消息显示出来，命令的回答是它自己的
一条消息——agent 的回答不会被它顶掉。

agent 正在干活的时候敲命令会被拒绝：它会说
`The agent is working. Wait for it, or press ctrl+c to stop it.`，命令不会跑。
等这一轮结束，或者按 `ctrl+c` 把 agent 停掉。

## 内置命令

| 命令 | 干什么 | 收什么 |
|---|---|---|
| `/help` | 命令的列表 | `[name]` |
| `/model`（`/m`） | 看或者换模型 | `[model-name]` |
| `/mode` | 看或者换权限模式 | `[default\|acceptEdits\|plan\|bypass\|readonly]` |
| `/plan` | 切到 plan 模式，什么都不改 | |
| `/compact` | 现在就压缩对话 | |
| `/recap` | 总结一下对话，但什么都不改 | |
| `/side` | 在一段岔开的对话里问一个问题 | `<question>` |
| `/clear` | 开一个新会话 | |
| `/resume` | 列出会话，或者续接一个 | `[session-id]` |
| `/fork` | 把会话复制成一个新会话 | `[session-id]` |
| `/rename` | 给会话起个名字 | `[name]` |
| `/archive` | 把会话收起来，或者再拿出来 | `[session-id]` |
| `/delete` | 删掉一个会话和它的全部内容 | `<session-id>` |
| `/rewind` | 列出检查点，或者退回去一个 | `[checkpoint-id]` |
| `/diff` | 看工作区里的改动 | |
| `/review` | 审查改动，或者审查一个范围的改动 | `[main..HEAD]` |
| `/image` | 给 agent 发一张图片 | `<path> [要它做什么]` |
| `/mention` | 给 agent 发一个文件，带着内容 | `<path> [要它做什么]` |
| `/open` | 在用户自己的编辑器里打开一个文件 | `<path>` |
| `/init` | 给这个项目写一个 `AGENTS.md` | |
| `/cost` | 已经花掉的 token 和钱 | |
| `/todos` | agent 的任务清单 | |
| `/mcp` | MCP 服务器和它们的状态 | |
| `/permissions` | 现在生效的规则 | |
| `/hooks` | 加载了的 hook | |
| `/agents` | 可以用的子 agent | |
| `/skills` | 可以用的技能 | |
| `/plugins` | 插件，或者信任其中一个 | `[trust <name>]` |
| `/trust` | 项目里等着用户决定的代码，或者信任它 | `[number]` |
| `/memory` | 项目的记忆和用户的记忆 | `[confirm\|forget <text>]` |
| `/status` | 会话的状态 | |
| `/sandbox` | agent 的命令在哪里跑 | |
| `/export` | 把对话写成文件 | `[path]` |
| `/context` | 上下文有多大 | |
| `/exit`（`/quit`） | 退出界面 | |

第三列就是 `/help` 打印的东西：命令能收什么写在列里，不用记。`/help <名字>`
讲一个命令，顺带说它收什么。项目自己的命令（见下）也在列表里，带着它的文件
里声明的参数。

`/cost` 里的钱就是会话的钱。新会话（`/clear`）从零开始，不管上一个会话花了
多少。

`/review` 让模型看一遍改动，说出哪里有问题。不带范围时审的是工作区里的改动，
带范围时（`/review main..HEAD`）审的是那个范围。新加的、还没进版本库的文件
会被单独点名，模型觉得重要就自己去读。审查是当前会话里的一轮：结果留在对话里，
你可以接着说「把第二条改掉」。审查的时候模型被要求不改任何文件。

diff 本身不进上下文：这一轮里模型看得到，轮结束后换成一句话，说改动不在了、
要自己再读一遍文件。不然一次大 diff 就把整个会话的窗口吃掉了。

审查可以跑在另一个模型上：`model.review_model` 写它的名字，`model.routing.review`
压过它。两个都没写就还是会话自己的模型。

`/image` 把一张图片发给模型。路径是第一个词，后面都是跟图片一起的话：

```bash
/image screenshot.png 这个布局哪里不对？
```

图片原样发过去：`png`、`jpg`、`gif`、`webp` 是模型那边认的格式，超过 5 MB 的
文件会被拒绝，而不是硬发过去。图片和文本一样算 token，所以上下文会按图片的大小
变大。模型的回答像别的轮次一样留在对话里。

`/mention` 把一个**文件**发给模型，内容直接进消息，模型不用再花一次工具调用
去读它：

```bash
/mention src/app.py 这个文件做什么？
```

提问里点名文件也是一样：`看看 @src/app.py` 会把文件内容放进消息。不存在的
名字就当没写，所以邮箱和装饰器不会被打开。

这里权限的边界照样管着：工作目录外面的文件、规则拒绝的文件，都不进消息。
消息里写的是「agent 读不了这个文件」。

`/exit` 关掉终端界面，和 `ctrl+q` 一样。浏览器里没有东西可关，所以它会说
服务还在跑：要停掉它，得在启动它的那个终端里按 `ctrl+c`。

## 一份总结，和一段岔开的对话

`/recap` 把到现在的对话总结一遍，把总结给你看：目标、发现、决定、动过的文件、
还没解决的问题、下一步。

```bash
/recap
```

什么都不会被丢掉，也不会被压缩：模型看到的还是整段对话，总结本身不进它的上下文。
这是一份给你看的报告，不是干活的一步。总结要花一次模型调用，这笔钱记在会话上，
用途是 `recap`。

`/side` 在一段自己的对话里问一个问题：

```bash
/side 客户端的重试逻辑是怎么做的？
```

这段对话是你当前会话的一份拷贝，有自己的日志。问题和回答会记在你当前会话里，
所以 agent 不会丢掉干活的线索，但也就这些：岔开的那些消息留在岔开的会话里，
它用的工具也算在那个会话上。

岔开的会话有自己的 id，跟别的会话一样可以打开（`/resume <id>`）。它花的钱记在
你当前会话上，用途是 `side`。

## 会话的一生

会话有名字，可以收起来，也可以删掉：

```bash
/rename monday 那个 bug   # 给当前会话起个名字
/archive                 # 把这个会话收起来
/archive <session-id>    # 把另一个收起来
/delete <session-id>     # 删掉它和它的全部内容
```

收起来的会话不再出现在 `/resume` 的列表里，但它还在盘上，
`/resume <session-id>` 照样能打开。已经收起来的会话再跑一次 `/archive`
就又拿出来了。

`/delete` 要会话的 id，而且**不删你正待着的那个会话**：先 `/clear` 开一个新的。
会话里的一切——事件日志和它的元数据文件——一起没了。

## 用户自己的文件

`/open` 在用户自己的编辑器里打开一个文件：

```bash
/open src/app.py
```

编辑器由配置决定：

```yaml
ui:
  file_opener: vscode
```

`vscode`、`cursor`、`windsurf` 这些名字是认识的。用户自己的命令也行，
用 `{file}` 告诉它文件放在哪：`my-editor {file} --wait`。文件必须在工作目录
里面，而且**项目不能挑编辑器**——那个程序跑在用户的机器上，这个选择归用户。

## 自己的命令

一个命令就是 `.coderagent/commands` 里的一个 markdown 文件。文件开头是 front
matter，和 Claude Code 一个写法：

```markdown
---
description: Generate a commit message
argument-hint: [file]
allowed-tools: bash(git diff:*), read
---
Describe the change of $1.
Everything else: $ARGUMENTS
```

- `$ARGUMENTS` 变成用户敲在命令后面的全部内容。
- `$1`、`$2`…… 变成参数，一个一个来。
- `allowed-tools` 限定这个命令能用的工具。命令干完，session 的工具就回来了。
- `model` 给这个命令换一个模型。

括号里那一段**本身就是一道限制**：`bash(git diff:*)` 是说这个命令只能跑
`git diff`，别的都跑不了；没写出来的工具就是没有。这个限制在哪种权限模式下
都在，用户的规则也不能把它放宽。

上面那个命令这么用：

```bash
/commit src/coderagent/core/loop.py
```

没有 front matter 的文件会被忽略。命令在 `<cwd>/.coderagent/commands/*.md`
和 `~/.coderagent/commands/*.md` 里找——agent 不会一层层往上找。同名时项目
里的那个算数。
