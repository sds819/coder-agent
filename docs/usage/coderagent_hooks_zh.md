# Hooks

hook 是用户自己写的命令，在会话的关键时刻跑一次。它可以拦住一次操作、改写它的参数，或者给模型补一点上下文。

> 英文版：[Hooks](coderagent_hooks.md)

## 配置

```yaml
hooks:
  events:
    PreToolUse:
      - matcher: "bash"
        hooks:
          - type: command
            command: ./scripts/guard.sh
            timeout: 10
    PostToolUse:
      - matcher: "edit|write"
        hooks:
          - type: command
            command: ruff format {file}
```

| 键 | 是什么 | 默认值 |
|---|---|---|
| `type` | hook 的种类。只实现了 `command` | `command` |
| `matcher` | 工具名的正则。空表示所有工具 | |
| `command` | 要跑的命令，用 shell 跑，在会话的目录里 | |
| `timeout` | 最多跑多久，单位是秒 | 10 |
| `strict` | hook 失败时拦住这次操作，而不是放行 | false |

项目的 hook 写在 `.coderagent/config.yaml`，用户的 hook 写在 `~/.coderagent/config.yaml`。插件也可以带 hook。
两个文件像其它配置一样合并：事件是合并的，但同一个事件下 hook 的那份列表会被用户那份整个换掉。

**项目里**的 hook 是没人问过就跑起来的程序，所以它先等一个决定。**用户**的 hook 是用户自己的，
照用不误。见[项目里的代码](coderagent.md#the-code-of-a-project)。

`matcher` 是拿工具名去匹配的，所以它只对 `PreToolUse` 和 `PostToolUse` 有意义。其它事件留空就行。
它是**搜出来的正则，不是从头对上的**：工具名 `multi_edit` 会被 `edit|write` 匹配上；大小写敏感，
所以 `Bash` 什么也匹配不到。正则本身写坏了会记一条日志，然后什么也不匹配。

## 九个时刻

| Hook | 什么时候 | 能做什么 |
|---|---|---|
| `SessionStart` | 会话开始 | 什么也不做，是个通知 |
| `UserPromptSubmit` | 拿到提问之后、问模型之前 | 补上下文、改写提问，或者拦住提问 |
| `PreToolUse` | 工具跑之前 | 拒绝，或者改写参数 |
| `PostToolUse` | 工具跑完之后 | 补上下文，或者把结果拦下来 |
| `Stop` | agent 想停下来 | 让它回去接着干 |
| `SessionEnd` | 这一轮结束 | 什么也不做，是个通知 |
| `PreCompact` | 压缩历史之前 | 什么也不做，是个通知 |
| `PostCompact` | 压缩历史之后 | 什么也不做，是个通知 |
| `SubagentStop` | 子 agent 干完之后 | 什么也不做，是个通知 |

`SessionEnd` 是每一轮结束时都跑，不是只在整个会话结束时。

每个事件读到的内容不一样：

| Hook | 读到什么 |
|---|---|
| `SessionStart` | `session_id`、`cwd` |
| `UserPromptSubmit` | `prompt` |
| `PreToolUse` | `tool`、`params` |
| `PostToolUse` | `tool`、`params`、`result` |
| `Stop` | `last_message` |
| `SessionEnd` | `session_id`、`turns`、`cost` |
| `PreCompact` | `messages`（马上要压掉的那几条）、`turn` |
| `PostCompact` | `summary`、`messages`（压掉了几条）、`tokens`、`summary_tokens` |
| `SubagentStop` | `agent`、`status`、`summary`、`files_touched` |

后这三个是**通知**：它们改不了什么。`PreCompact` 和 `PostCompact` 是量摘要
质量的地方——前一个看得见马上要走的消息，后一个看得见换回来的摘要和它花了
多少 token。

## hook 怎么回答

hook 从标准输入读这些细节，把答案写成 JSON 写到标准输出：

```python
#!/usr/bin/env python3
import json
import sys

payload = json.load(sys.stdin)
if payload.get("tool") == "bash" and "rm -rf" in payload["params"].get("command", ""):
    print(json.dumps({"decision": "deny", "reason": "that command is not allowed"}))
```

可以写的键：

- `decision`：`allow`、`deny` 或 `block`。**只有 `deny` 和 `block` 会被看**——
  `allow` 什么也不做：它既不会批准这次调用，也不会跳过权限检查。
- `reason`：为什么。它会作为工具的错误回到模型那里。
- `additionalContext`：给模型看的一句话。
- `updatedInput`：这一刻的新输入。`PreToolUse` 里它是一个映射，替换掉工具的参数；
  `UserPromptSubmit` 里它是一个字符串，替换掉用户的提问。`PostToolUse` 里工具已经跑完了，
  给映射也换不了什么。

标准输出是空的，意思就是这个 hook 没有意见。几个 hook 的答案会合并起来：`deny`
压过其他一切，上下文拼在一起，`updatedInput` 取最后一个。

## 答案会做什么

| 答案 | 会发生什么 |
|---|---|
| `PreToolUse` 拒绝 | 这次工具调用失败，理由回到模型那里 |
| `PreToolUse` 改写参数 | 工具用新的参数跑 |
| `PreToolUse` 允许 | 什么也不发生。权限检查照旧 |
| `PostToolUse` 拒绝 | 回给模型的那条消息变成一个错误，日志里工具的结果照旧 |
| `PostToolUse` 补上下文 | 上下文追加到工具的结果后面 |
| `UserPromptSubmit` 拒绝 | 这一轮以错误结束，模型根本不被调用 |
| `UserPromptSubmit` 补上下文 | 上下文追加到提问后面 |
| `UserPromptSubmit` 改写提问 | 模型看到的是新提问，日志里两个都留着 |
| `Stop` 拒绝 | agent 接着干，理由作为一条新消息给它（每轮最多三次） |

`PreToolUse` 的 hook 跑在**权限检查之前**，所以被批准的是被改写之后的那条命令。

## Stop hook

`Stop` hook 只被问一个问题：agent 现在能停吗？agent 想停的时候，是它回答里没有
工具调用的时候。hook 从 `last_message` 里读到那段回答，答 `block`（或 `deny`）就
是让它回去接着干。

```python
#!/usr/bin/env python3
import json
import sys

payload = json.load(sys.stdin)
if "TODO" in payload.get("last_message", ""):
    print(json.dumps({"decision": "block", "reason": "还有 TODO 没处理完，先处理它们。"}))
```

理由会作为一条 **user** 消息回到模型那里，前面带着 `[hook]`。这是建议，不是命令：
模型可以再停一次。所以这个 hook **一轮最多被问三次**——过了三次，agent 停不停
由它自己定，这一轮里也不会再问这个 hook 了。

`Stop` 上各个键的作用：

| 键 | 在 `Stop` 上的作用 |
|---|---|
| `decision` | 只有 `block` 和 `deny` 有用。`allow` 什么也不做 |
| `reason` | 作为一条新消息回到模型那里 |
| `additionalContext` | **没有作用**——只用了理由 |
| `updatedInput` | **没有作用**——这里没有东西可以改写 |

几件容易让人意外的事：

- **`matcher` 必须留空。** matcher 是拿工具名去匹配的，而 `Stop` 的内容里没有工具。
  像 `bash` 这样的 matcher 什么也匹配不上，于是这个 hook 永远不会被调用——而且没有
  任何提示。留空（或者写 `.*`）。
- **子 agent 不受它管。** `Stop` hook 只有主 agent 会问。子 agent 想停就停了；
  `SubagentStop` 是个通知，改不了什么。
- **它排在另外两道闸门前面。** 顺序是 `Stop`、然后是校验的命令、然后是答案的
  schema。被 hook 拦下的那次停，两个都不查。
- **每拦一次，模型就多调一次。** 拦停会把 agent 送回模型，而这一轮的限额
  （`max_turns`、`cost_limit`、`token_limit`）在下次调用之前会重新判一遍。老是拦的
  hook 能把一轮变成 `max_turns`。
- **三次是这一轮的。** 用户下一个提问，又是三次。
- **`strict: true` 能让 agent 停不下来。** 以非零退出码结束的 `Stop` hook 会拒绝这次
  停，于是坏掉的 hook 让 agent 一直干活——直到第三次拦停，之后 agent 还是会停。

## 一个改写提问的 hook

```python
#!/usr/bin/env python3
import json
import sys

payload = json.load(sys.stdin)
print(json.dumps({"updatedInput": payload["prompt"] + "\n\n用中文回答。"}))
```

模型从头到尾看不到用户原话，只看到改写后的那份。事件日志里存的是**模型看到的那份**，
这样重放这个会话时说的一样的话；用户原话放在同一条记录的 `original` 里。网页版里，
气泡显示用户写的话，下面一行小字说明给 agent 的是什么。

`PreToolUse` 的 hook 如果回答一个字符串 `updatedInput`，什么也不会发生：只有映射
才能替换工具的参数。

## hook 失败的时候

hook 崩了、超时了，或者写出来的东西不是 JSON，都会被忽略：操作照旧进行。

`strict: true` 只改一件事：以非零退出码结束的 hook 会拦住这次操作，它的标准错误
就是理由。超时和坏掉的答案两种情况下都被忽略。
