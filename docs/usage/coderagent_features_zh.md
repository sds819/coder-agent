# coding agent 的功能

`coder` 有什么本事，一条一条写下来。每一节最后都给出讲得更细的文档，每一节
都有用法例子和出错时怎么办。

> English: [The features of the coding agent](coderagent_features.md)

## 怎么用

- **终端里跑一轮**——`coder -t "把失败的测试修好"`。结果按文本打印，
  加 `--output-format json` 就是 JSON。
- **跑一轮，答案有形状**——`coder -t "..." --output-schema answer.json`。
  答案是对得上那个 schema 的 JSON，一轮的 JSON 里放在 `output` 字段。
- **跑一轮，答案进文件**——`coder -t "..." --output-last-message answer.md`。
  文件里只有 agent 最后那句回答，别的东西都没有。
- **终端界面**——不给任务就是 `coder`，也可以 `coder --tui`。全屏界面，
  有状态栏、工具卡片和审批。
- **浏览器里**——`coder web`。同一个 agent，一个聊天页，一个设置模型配置
  的设置页。
- **当 API 用**——浏览器做的每个动作都是普通 HTTP 调用，脚本也能驱动它。
- **当库用**——`coderagent.run.run_turn` 和 `build_loop` 把 agent 放进别的
  Python 程序里。

agent 在干活的时候，终端、终端界面和浏览器里都是同一串长长短短的点。那是
「它在忙」的信号：它没说话，但它没卡住。

### 用法例子

```bash
# 跑一轮，答案是文本。
coder -t "给 src/app.py 加个 docstring"

# 跑一轮，答案是 JSON（给脚本用）。
coder -t "列一下这个目录里的文件" --output-format json

# 跑一轮，答案是对得上 schema 的 JSON。
coder -t "列一下这个目录里的文件" --output-schema files.json

# 跑一轮，答案写进文件。
coder -t "列一下这个目录里的文件" --output-last-message answer.md

# 终端界面。
coder                      # 在终端里这就是 TUI
coder --tui                # 明确写出来

# 浏览器。
coder web --cwd . --port 8765

# 这个目录的会话，最新的在前。
coder --list
```

一轮的 JSON 有这些字段：`session_id`、`messages`、`cost`、`session_cost`、
`stop_reason`、`error`、`output`。

```json
{
  "session_id": "20261109-3f0a91",
  "messages": [{"role": "assistant", "content": "我把 docstring 加上了。"}],
  "cost": 0.0012,
  "session_cost": 0.0143,
  "stop_reason": "end_turn",
  "error": "",
  "output": null
}
```

`cost` 是这一轮花了多少，`session_cost` 是整个会话到目前为止花了多少。
`output` 是给了 schema 时的答案，没给 schema 时是 `null`。

`stop_reason` 是 `end_turn`、`max_turns`、`cost_exceeded`、`token_limit`、`verify_failed`、
`schema_invalid`、`error`、`interrupted` 之一。

### 答案是有形状的

`--output-schema` 接一个装着 JSON schema 的文件。agent 的答案必须对得上它，
而且这个检查是 agent 自己做的，不是模型服务端做的：

```json
{
  "type": "object",
  "properties": {"files": {"type": "array", "items": {"type": "string"}}},
  "required": ["files"],
  "additionalProperties": false
}
```

认的关键字是 `type`（一个名字或者一串名字）、`properties`、`required`、
`additionalProperties`、`items`、`enum`、`nullable`。用了别的关键字不报错，
只是那部分不检查。

模型一开始就知道这个 schema；对不上的答案会**连着错在哪儿一起退回去**，
让它改一次。它有两次机会；第二次还是对不上，这一轮就以 `stop_reason`
`schema_invalid` 停下，错在 `error` 里。

#### 查什么，不查什么

检查是 agent 自己那个小校验器做的，不是模型服务端做的。模型只是**被要求**给出对得上
schema 的 JSON——schema 在系统提示词里——答案出来之后才查。模型服务端从来没见过
这个 schema，所以模型不听话的代价是一次重试。

校验器只认这几个关键字：

| 关键字 | 做什么 |
|---|---|
| `type` | 一个名字或者一串名字：`string`、`integer`、`number`、`boolean`、`object`、`array`、`null` |
| `properties` | 字段的类型，就地检查 |
| `required` | 这个字段必须在 |
| `additionalProperties: false` | schema 里没有的字段算错 |
| `items` | 数组的元素，逐个查 |
| `enum` | 值必须是列表里的一个 |
| `nullable` | 允许 `null` |

其它关键字（`anyOf`、`$ref`、`pattern`、`minimum`……）**一律忽略**：用到它们的那部分
不检查，答案也不被拒绝。靠它们的 schema 看着很严，其实不严。

校验器在两件事上很严：

- 布尔不是数字——`{"count": true}` 对不上 `{"count": {"type": "integer"}}`；
- `nullable` 只是把 `null` 加进允许的值里，并不放松类型——
  `{"type": "integer", "nullable": true}` 照样不接受 `""`。

错误会指出答案错在哪儿，模型才知道该改什么：`'files[1]' must be string`、
`the answer is missing 'files'`、`the answer has the unknown field 'extra'`。

#### 怎么从文本里读出答案

模型的回答是文本，JSON 是从里面取出来的：

1. 整段就是 JSON——直接用；
2. 外面包了一层代码围栏——把围栏脱掉；
3. 前面有一句话——取第一个 `{` 到最后一个 `}` 之间那部分。

顶层是**数组**时，整段就是数组才读得出来。数组外面带一句话的话，它不会被当成数组读：
第三条规则找的是花括号，于是取到的是第一个 `{` 到最后一个 `}` 之间那部分——数组**里面**
那个对象。检查会说这不是数组，于是模型被叫回来再答一次。

#### 两次答案

模型有两次机会。第一次对不上，会**连着错在哪儿一起退回去**，作为一条新消息给它——
所以 agent 是被叫回去，不是被拦住。第二次还是对不上，这一轮就以 `stop_reason`
`schema_invalid` 结束，错在 `error` 里，`output` 还是 `null`。

这个形状是三道闸门里的最后一道：`Stop` hook 和校验命令排在前面，所以被它们叫回去的
那一轮根本走不到检查。这个形状属于这个循环，不属于某一段对话：切会话它也还在。

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `no task given` | 没有 `-t`，也没有 `--tui`，而且 stdin 不是终端（脚本、管道）。 | 给个任务：`coder -t "..."`。 |
| `session 20261109-3f0a91` | 同上，但找到了可以续上的会话。 | 一样，加上 `-t` 就在里面跑一轮。 |
| `Unknown command '/foo'. Try /help.` | 这一行以 `/` 开头，但没有这个命令。 | 检查拼写，或者 `/help` 看列表。 |
| `ValueError: 'bogus' is not a valid PermissionMode` | `--permission-mode bogus`——这个值在建立权限策略时才检查，异常没有被捕获。 | 用 `default`、`acceptEdits`、`plan`、`readonly`、`bypass` 之一。 |
| `ValueError: Unknown output format: xml` | `--output-format` 只认 `text` 和 `json`。 | 用 `text` 或 `json`。 |
| `Invalid value: the schema file is not valid JSON: ...` | `--output-schema` 指的那个文件里不是 JSON。 | 把文件改对，或者去掉这个标志。 |
| `Invalid value: the schema file cannot be read: ...` | `--output-schema` 指的那个文件不在。 | 检查路径。 |
| `stop_reason` 是 `schema_invalid` | 模型两次都没给出对得上 schema 的 JSON。 | 错在 `error` 里，这一轮的消息里写了模型被告知了什么。 |
| 检查过了，但答案不是你要的 | schema 用了校验器不认的关键字（`anyOf`、`$ref`……），那部分根本没查。 | 用上面那几个关键字写 schema，答案在 `output` 里。 |
| `Unknown format 'xml'. Use json or otel.` | `coder export --format` 只认 `json` 和 `otel`。 | 用 `json` 或 `otel`。 |
| `no sessions yet` | `--list` 在这个目录里没找到会话。 | 不用管，先跑一轮。 |
| stderr 上的 `coder web: cannot listen on 127.0.0.1:8765 (Address already in use).`，退出码 1 | 端口被占。服务启动前自己先探一下，因为 uvicorn 自己的报错不告诉你该怎么办。 | 换一个端口：`coder web --port 8766`。 |

正常跑完一轮 `coder` 的退出码是 `0`，不管答案是什么；连启动都没成功时
（标志的值不对、端口被占）是 `1`。

## 模型

- **litellm 认识的任何厂商**——OpenAI、DeepSeek、Anthropic、Gemini、
  Mistral、OpenRouter……厂商可以写在名字前面（`deepseek/deepseek-flash`），
  也可以不写：由接口地址和模型系列来定。
- **第三方端点**——`api_base` 里写一个 OpenAI 兼容的地址，配它自己的 key。
  地址可以直接粘完整的 `/chat/completions`，`/v1` 后面那段会被剪掉，
  因为 litellm 自己会加。
- **别名**——一个带模型列表的 litellm 配置文件。模型名可以是那个列表里的
  一条别名，端点的 key 就留在那个文件里。
- **缓存标记**——`set_cache_control: default_end`，给支持它的厂商用。别的值会被拒。
- **模型想多久**——`reasoning_effort`：`minimal`、`low`、`medium`、`high`，
  留空就是模型的默认。这个档位会翻译成厂商认识的说法：OpenAI 那些是
  `reasoning_effort`，Anthropic 是一笔 token。
- **模型说多少**——`verbosity`：`low`、`medium`、`high`，留空是模型自己的
  习惯。这个档位是一句写进系统提示词的话，所以哪家厂商都听得懂。
- **评审用别的模型**——`model.review_model`。路由里没有 `review` 时，
  `/review` 就跑在那个模型上。
- **重试**——`max_retries`，默认三次，终端和浏览器一样。
- **按用途路由**——`main`、`cheap`、`summarize`、`reflect`、`strong`、`review`
  可以各配一个模型。
- **按会话状态路由**——像 `tokens > 50000` 这样的规则会换模型，理由写在
  事件日志里。
- **摘要用别的模型**——`context.summarize_model`，留空就是 agent 自己那个。
- **流式输出**——答案一段一段到，终端和浏览器都是。

### 用法例子

```bash
# 厂商写在名字前面（也可以不写，由地址和模型系列来定）。
coder -t "..." -m deepseek/deepseek-flash

# 一个说 OpenAI 协议的第三方端点。
coder -t "..." -m openai/MiniMax-M2.7 \
  -c model.api_base=https://api.example.com/v1 \
  -c model.api_key=sk-...
```

```yaml
# ~/.coderagent/config.yaml
model:
  model_name: deepseek/deepseek-flash
  set_cache_control: default_end
  reasoning_effort: medium
  verbosity: low
  review_model: anthropic/claude-sonnet-4-5
  routing:
    main: deepseek/deepseek-chat
    cheap: deepseek/deepseek-flash
    summarize: deepseek/deepseek-flash
  routing_rules:
    - when: "tokens > 50000"
      purpose: strong
```

一轮用哪个模型，按这个顺序定：

1. 用户用 `/model` 选的模型（它压过所有别的东西），
2. 第一条成立的 `routing_rules`，
3. 自动策略：预算快用完了 → `cheap`，上下文太大（超过 50000 token）或
   会话太长（超过 30 轮）→ `strong`，
4. `routing.main`，没有它就是 agent 自己的模型。

换了模型，事件日志里会写理由：

```
Switched from deepseek/deepseek-flash to deepseek/deepseek-chat: the context has grown
```

理由有这些：`the budget is nearly used up`、`the context has grown`、
`the session has many turns`、`the rule '<when>' holds`、
`the rules of the routing say so`。

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `LLM Provider NOT provided` | 名字里没有厂商，接口地址和模型系列也说不出来。 | OpenAI 兼容的端点写 `openai/<名字>`，或者 `deepseek/<名字>`。 |
| `ValueError: Invalid mode: {mode}` | `set_cache_control` 既不是 `default_end`，也不是空的。 | 用 `default_end`，或者删掉这一行。 |
| `unknown reasoning effort '{level}'` | `reasoning_effort` 不是 `minimal`、`low`、`medium`、`high` 里的一个。 | 用那四个里的一个，或者删掉这一行（用模型的默认）。 |
| `unknown verbosity '{level}'` | `verbosity` 不是 `low`、`medium`、`high` 里的一个。 | 用那三个里的一个，或者删掉这一行（用模型自己的习惯）。 |
| `'model_kwargs' must not have '{key}'` | `model_kwargs` 里有这次调用的参数：`model`、`messages`、`tools`、`stream` 或 `stream_options`。 | 删掉它：这些是 agent 自己设的。 |
| `the file does not exist` | `model.litellm_config` 指的文件不在。 | 改路径：相对路径先在 `~/.coderagent/` 里找，再在工作目录里找。 |
| `the file is not valid YAML: {error}` | 别名文件解析不了。 | 修 YAML。 |
| `the file has no model_list` | 别名文件里没有 `model_list`。 | 加上模型列表和它们的 `litellm_params`。 |
| `'{name}' is not one of the aliases of this file` | 模型名不在这个文件的 `model_list` 里。 | 用列表里的别名，或者去掉 `litellm_config`。 |
| `The model '{name}' is not one of the aliases of {file}` | 模型名不在这个文件的 `model_list` 里，所以这个文件的设置一个都没用上。 | 用列表里的别名，或者去掉 `litellm_config`。 |
| `BadRequestError` | 厂商拒绝了请求（key 不对、名字不对、参数不对）。 | **不会**重试，厂商的报错就是答案。 |
| `AuthenticationError` | key 缺了或者不对。 | 设 `model.api_key`，或者在别名文件里写端点的 key，或者在环境里放厂商的 key（`openai/…` 找 `OPENAI_API_KEY`）。 |
| `ContextWindowExceededError` | 请求比模型的窗口大。 | 调小 `context.context_window`，或者换一个窗口更大的模型。 |

重试和上面的错误是两回事：限流和超时才重试，坏请求不重试。重试次数来自
`model.max_retries`（默认 3），终端和浏览器都一样。环境变量
`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT` 能盖过它——测试不想等的时候好用。

## 配置

配置分四层读，后面的赢：内置默认值、项目的 `.coderagent/config.yaml`、用户的
`~/.coderagent/config.yaml`、命令行上的 `-c key=value`。

没有意义的设置会被**拒绝**，不会悄悄收下：

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `unknown permission mode '{name}'` | `permissions.mode` 不是那五个模式之一。 | 用 `default`、`acceptEdits`、`plan`、`bypass` 或 `readonly`。 |
| `unknown network policy '{name}'` | `permissions.network` 不是 `allow` 或 `deny`。 | 用这两个之一。 |
| `unknown tool '{name}'` | `tools.enabled` 或 `tools.disabled` 写了一个不存在的工具。 | 用内置工具的名字。 |
| `unknown hook event '{name}'` | `hooks.events` 写了一个不是「会话时刻」的时刻。 | 用 [Hooks](coderagent_hooks_zh.md) 里的事件。 |
| `unknown purpose '{name}'` | `model.routing` 或一条路由规则写了一个不存在的用途。 | 用[路由](coderagent_routing.md)里的用途。 |
| `'{name}' is not a condition` | 一条路由规则不是「键 运算符 数字」。 | 写成 `tokens > 50000` 这样。 |
| `Extra inputs are not permitted` | 段名或键名写错了（`permissons`）。 | 把名字改对。 |
| `Input should be greater than or equal to 0` | 数字是负的。 | 用零或更大的数。 |

**项目**和用户不一样：仓库不能弄坏用户的会话，所以它写错的地方被一个键一个键地
丢掉，文件里其余的部分照旧。项目也只能把会话的天花板调低，不能调高。

## 工具

十四个内置工具：

| 工具 | 干什么 |
|---|---|
| `read` | 读文件，带行号 |
| `write` | 写文件，没有就建 |
| `edit` | 替换文件里一处完全一样的字符串 |
| `multi_edit` | 一个文件里多处改动——要么全成，要么全不成 |
| `apply_patch` | 打一个带上下文的补丁——一次改多个文件，也能建和删 |
| `glob` | 按模式找文件（`*` 在一段里，`**` 跨目录） |
| `grep` | 用正则搜内容，可以要匹配的行、文件名或者计数 |
| `ls` | 列目录；`depth: -1` 是整棵树 |
| `bash` | 跑一条命令，可以带超时，也可以放到后台 |
| `bash_output` | 后台命令到目前为止的输出 |
| `bash_kill` | 杀掉后台命令 |
| `todo_write` | 这一轮要做的事 |
| `task` | 把一件自成一体的事交给子 agent |
| `skill` | 载入一个技能的说明 |

- **MCP 服务器的工具**——`mcp__<服务器>__<工具>`，配了的服务器都有。
- **MCP 服务器的工具可以挑**——`enabled_tools`（只露这些）和 `disabled_tools`
  （这些不露）能按名字筛一个服务器的工具，`*` 表示全部。没露出来的工具模型根本
  看不见。
- **插件的工具**——插件可以加工具、命令和 hook。
- **工具的 schema 会按预算裁剪**——工具的 schema 最多占上下文的十分之一（`tools.schema_budget_tokens` 可以另设预算）；塞不下时最不重要的先走。
  `bash` 和 `read` 永远不裁。
- **工具集可以配**——`tools.enabled` 是模型能调的工具清单，`tools.disabled`
  是单独拿掉几个。
- **每个结果都按预算裁**——`tools.max_output_tokens`（默认 8000）是一条工具
  结果的大小上限。太长的留下头和尾，中间写明裁掉了什么。完整的结果还留在会话
  日志里。
- **命令看不见你的 key**——命令的环境本来是你的，但名字像秘密的那些
  （`*_API_KEY`、`*_TOKEN`……）会被去掉。`shell_environment` 决定 agent 能看见
  多少。

### 用法例子

模型会调这些工具，你也可以自己调来试：

```json
{"tool": "read", "params": {"path": "src/app.py"}}
{"tool": "edit", "params": {"path": "src/app.py", "old_string": "x = 1", "new_string": "x = 2"}}
{"tool": "grep", "params": {"pattern": "def main", "output_mode": "files_with_matches"}}
{"tool": "glob", "params": {"pattern": "src/**/*.py"}}
{"tool": "ls", "params": {"path": "src", "depth": -1}}
{"tool": "bash", "params": {"command": "pytest -q", "timeout": 300}}
{"tool": "bash", "params": {"command": "pytest -q", "run_in_background": true}}
{"tool": "bash_output", "params": {"task_id": "b7f3"}}
```

`multi_edit` 收一个列表，要么全成要么全不成：

```json
{"tool": "multi_edit", "params": {"path": "src/app.py", "edits": [
  {"old_string": "import os", "new_string": "import os\nimport sys"},
  {"old_string": "def main():", "new_string": "def main(argv=None):"}
]}}
```

`apply_patch` 收一个带上下文的补丁，Codex 就是这么写的。一次能改好几个文件，
而且是**要么全成要么全不成**：有一处对不上，一个文件都不动。

```
*** Begin Patch
*** Update File: src/app.py
@@ def main():
 def main(argv=None):
-    run()
+    run(argv)
*** Add File: notes.md
+the notes of the change
*** Delete File: old.py
*** End Patch
```

行首是空格的是留下的行，`-` 开头的删掉，`+` 开头的加上。`@@` 后面那段是
「这块大概在哪儿」的提示，真正要对上的是那一段上下文。补丁也能删文件，
最后一行是 `*** End Patch`。

`grep` 有三种模式：`content`（默认）、`files_with_matches`、`count`。
它最多返回 100 条匹配，`glob` 最多 200 个文件。

指向工作目录以外的链接不会被跟过去：`grep` 会跳过它，所以指向
`~/.ssh/id_rsa` 的链接读不出来。`ls` 显示的是链接自己，不是它指的那个文件。

### 出错时怎么办

每个工具都不抛异常，而是回答一行 `Error: ...`，模型看得见这句话，可以自己
改。消息长这样：

| 工具 | 消息 |
|---|---|
| `read` | `Error: file not found: {path}. Use \`ls\` to see what is in that directory.` |
| `read` | `Error: '{name}' is a directory. Use \`ls\` to list it.` |
| `read` | `Error: '{name}' is a binary file.` |
| `edit` | `Error: old_string not found in {path}. Use \`read\` to see the exact content, then retry with more context.` |
| `edit` | `Error: old_string is not unique in {path}: it appears {count} times (lines {...}). Include more surrounding context to make it unique, or set replace_all=true.` |
| `multi_edit` | `Error: Edit #1 failed, no changes were written. {inner}`——文件一个字节都没动。 |
| `apply_patch` | `Error: the patch must start with '*** Begin Patch'` / `Error: the patch must end with '*** End Patch'`——这压根不是个补丁。 |
| `apply_patch` | `Error: the context of the hunk does not match {path}: '{line}' is not where the patch says it is. Read the file again and use the lines that are really there.` |
| `apply_patch` | `Error: the file {path} exists already.`——要新建的文件已经有了。 |
| `apply_patch` | `Error: file not found: {path}.`——要改或者要删的文件不在。 |
| `apply_patch` | `Error: '{path}' is outside the working directory {cwd}.`——补丁跑到会话的目录外面去了。 |
| `grep` | `Error: invalid regular expression '{pattern}': {error}` |
| `grep` | `Error: \`output_mode\` must be one of content, files_with_matches, count (got '{mode}').` |
| `glob`/`grep`/`ls` | `Error: path not found: {path}.` / `Error: not a directory: {path}.` |
| `bash` | `Error: \`command\` is required and must be a non-empty string.` |
| `bash_output` | `Error: unknown task id '{id}'.` |
| `todo_write` | `Error: todo #1 has invalid status '{status}'. Use one of pending, in_progress, completed.` |
| `task` | `Error: unknown sub agent '{name}'. Available sub agents: {...}.` |
| `skill` | `Error: unknown skill '{name}'. Available skills: {...}.` |

执行器自己的错误写在调用的结果里：

| 消息 | 什么意思 |
|---|---|
| `Error: unknown tool '{name}'. Available tools: {...}.` | 模型调了一个没注册的工具——通常是 `tools.enabled` 被收窄了。 |
| `Error: permission denied for '{tool}'. {reason}` | 规则或者模式拒绝了这次调用。 |
| `Error: the user denied '{tool}'.` | 有人在审批那里按了 `n`。 |
| `Error: '{tool}' needs approval but no approver is available. Run with --permission-mode bypass to allow it.` | 这次调用需要审批，但是没有终端可以问。`--permission-mode bypass`，或者一条允许它的规则。 |
| `Error: the hook blocked '{tool}'. {reason}` | `PreToolUse` 的 hook 拒绝了这次调用。 |
| `Error: '{tool}' failed: {type}: {e}` | 工具自己抛了异常。 |

`bash` 的退出码不是零**不算错误**：退出码是输出的一部分，写成
`[exit code 1]`。命令跑得比 `tools.bash_timeout`（默认 120 秒）久，会失败
成：

```
An error occurred while executing the command: Command 'sleep 60' timed out after 120 seconds
```

放到后台的命令回答 `Started background task {id}: {cmd}`，用 `bash_output`
读，用 `bash_kill` 杀。它跑在会话的环境里，用的也是会话的环境。只有本地
环境能起后台任务：容器里这个调用会被拒绝，因为命令会跑到用户的机器上，
跑到会话的边界外面去。后台任务属于这个会话：会话的进程结束时它会被停掉，
它的日志也一起删掉。

工具的输出会写进会话日志，也会发给模型。里面长得像密钥的东西——API key、
token、密码、私钥——在写和发之前都会换成 `[redacted]`。日志里存的是模型看到
的那一份输出，按上下文的预算裁过，所以一个打印了几十 MB 的工具不会把会话
日志塞满。带密钥的文件存进 checkpoint 时会被去掉密钥，`/rewind` 也不会把
它恢复回去：文件保持原样，命令会告诉你是哪一个。

## 权限

- **五种模式**——`default`、`acceptEdits`、`plan`、`readonly`、`bypass`。
- **`bypass` 要问一次**——它把护栏全拆了，所以 `/mode bypass` 只说会做什么、
  什么都不改；`/mode bypass --yes` 才真的切过去。
- **`bypass` 没有上限**——钱（`agent.cost_limit`）、token（`agent.token_limit`）
  和模型调用的次数（`agent.max_turns`）在这个模式下都不拦这一轮：它一直跑到
  活干完，用户自己喊停。别的模式照旧拦。
- **模型会知道**——`plan` 和 `readonly` 下 agent 知道自己改不了东西，
  于是把看到的说出来，而不是动手。
- **规则**——`~/.coderagent/rules.yaml` 和 `.coderagent/rules.yaml` 按工具
  和模式决定放不放行。**用户级那份赢**，但 `deny` 谁也盖不掉。项目里的规则
  **只能拒绝**：项目不能自己给自己开权限。配置文件里的规则（`permissions.rules`）
  在读配置的时候就检查：决定值或键写错了，会在开场就停下来；项目里写坏的规则
  算成拒绝——写坏的拒绝不能变成放行。
- **`Always allow`**——审批卡片上的这个按钮会写一条规则，以后**同一个调用**
  （同一个文件、同一条命令）直接放行。
- **禁止的路径**——`permissions.deny_paths`，agent 不许碰的路径。命令行里
  提到它的命令也一样被拒。
- **额外的目录**——`permissions.include_dirs`，工作目录以外、agent 仍然
  可以碰的目录。
- **网络开关**——`permissions.network` 默认是 `allow`（出网的命令先问一次），
  `deny` 则**直接拒绝**。拒绝在**所有模式**下都成立，`bypass` 也不例外，
  用户级的规则也放宽不了它。项目里的配置**只能关网络，不能开网络**。
- **三个答案**——允许、拒绝、永久允许。没人回答就是拒绝：浏览器里等
  `ui.approval_timeout` 秒（默认五分钟），终端里一直等，因为那儿坐着人。
- **终端里用方向键选答案**，浏览器里点卡片上的按钮；没有终端时一律拒绝。
- **hook 跑在权限检查前面**——hook 可以改写这次调用或者拦下来，权限检查
  看到的是改写之后的那次。

### 用法例子

没有规则的时候，由模式决定：

| 模式 | `read`、`glob`、`grep`、`ls` | `write`、`edit`、`multi_edit` | `bash` | `todo_write`、`bash_output`、`bash_kill` |
|---|---|---|---|---|
| `default` | 允许 | 问 | 问¹ | 允许 |
| `acceptEdits` | 允许 | 允许 | 问¹ | 允许 |
| `plan` | 允许 | 拒绝 | 拒绝 | 允许 |
| `readonly` | 允许 | 拒绝 | 拒绝 | 允许 |
| `bypass` | 允许 | 允许 | 允许 | 允许 |

规则文件按工具和模式决定：

```yaml
# ~/.coderagent/rules.yaml
rules:
  - tool: bash
    pattern: "pytest"
    decision: allow
    reason: the test suite is safe to run
  - tool: edit
    pattern: "src/**/*.py"
    decision: allow
  - tool: "*"
    pattern: "*"
    decision: ask
```

`pattern` 对路径类工具是 glob（`*` 在一段里，`**` 跨目录），对 `bash` 是
**正则**，别的工具就是工具名。对 `bash`，这个正则要对上命令**每一段的开头**：
`git push` 能对上 `git push origin main`，但对不上 `echo "git push"`。

¹ 只是看的命令——`ls`、`cat`、`grep`、`git status` 之类——直接放行，不问；
其余的问。详见下面的[命令行](#cli)。

```bash
coder -t "跑一下测试" --permission-mode acceptEdits
coder -t "这个要怎么修？" --permission-mode plan
```

`plan` 和 `readonly` 会往给模型看的消息里塞一段说明：

```xml
<permission_mode mode="plan">
You are in plan mode. You may only look around: `read`, `glob`, `grep` and `ls`
work, but every tool that changes something, `bash` included, is refused.
Investigate the task and answer with the plan you would follow. The user
decides whether it is executed.
</permission_mode>
```

审批上的 `Always allow` 会往 `~/.coderagent/rules.yaml` 写一条规则：

```yaml
rules:
  - tool: bash
    pattern: pytest
    decision: allow
    reason: always allowed by the user
```

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `Error: permission denied for 'write'. '{path}' is outside the working directory {cwd}` | agent 想碰工作目录以外的路径。 | 把那个目录加进 `permissions.include_dirs`，或者换工作目录。 |
| `Error: the user denied 'write'.` | 有人在审批那里拒了。 | 允许它，或者为它写条规则。 |
| `Error: 'write' needs approval but no approver is available. Run with --permission-mode bypass to allow it.` | 这次运行没有终端（脚本或者 CI），而工具要审批。 | `--permission-mode bypass`，或者一条 `decision: allow` 的规则。 |
| `{path}:{line}: invalid decision '{d}', expected one of allow, ask, deny` | 规则文件里的决定值不对。 | 用 `allow`、`ask` 或 `deny`。 |
| `{path}:{line}: unknown rule keys: {keys}` | 规则里有不存在的键。 | 键只有 `tool`、`pattern`、`decision`、`reason`。 |
| `{path}: invalid YAML: {error}` | 规则文件解析不了。 | 修 YAML，消息里带着行号。 |
| `{path}: \`rules\` must be a list` | `rules` 不是一个列表。 | 写成一个由映射组成的列表。 |
| `Error: permission denied for 'bash'. '{path}' is outside the working directory {cwd}` | 命令里点了工作目录以外的路径。 | 用工作目录里的路径，或者用 `permissions.include_dirs` 打开那个目录。 |

`decision: allow` 的规则**不会**把整块磁盘打开：工作目录以外的路径还是
碰不到，除非它在 `permissions.include_dirs` 里。用户级的规则也不能放宽这个
边界。

匹配上的规则里**最严的赢**：`deny` 不会被后面的 `allow` 盖掉——项目级的规则
只能拒绝，那个拒绝也挡得住用户级的规则；`allow` 和 `ask` 之间是最后一条
匹配的赢。

`permissions.deny_paths` 拒绝所有匹配上的路径，它在规则文件之后生效，
所以同样路径上的 `allow` 打不过它。被禁止的路径对命令行也一样：禁掉
`*.env` 之后，`cat .env` 和 `read .env` 一样被拒。

### 命令行 {#cli}

`bash` 是唯一什么都能干的工具，所以它有三条边界。

**只是看的命令直接放行。** `ls`、`cat`、`head`、`tail`、`grep`、`diff`、`wc`、
`jq`，还有 `git` 里读东西的那些子命令（`status`、`diff`、`log`、`show`……）
是安全的：它们不改东西，也不联网，所以不问。

**会毁东西或者把东西送出去的命令要问。** `rm`、`mv`、`cp`、`chmod`、`curl`、
`wget`、`ssh`、`pip`、`npm`、`docker`、`git push` 这些。它们不是被拒绝——由
人来决定，审批上会写清楚这条命令干什么（「把数据送出这台机器」）。在
`bypass` 下它们照常放行，因为那儿没有人可问。

**工作目录以外的路径被拒绝。** `cat /etc/passwd`、`cat ../secret`、
`cat ~/.ssh/id_rsa`、`cd ..` 在任何模式下都被拒绝，和文件工具的路径一样。
系统的程序可以点名（`/bin/ls`），但数据不许离开工作目录。
`permissions.include_dirs` 可以打开工作目录以外的目录。

命令的每一段都单独判，取最严的那一段：放行了 `pytest` 也不代表跟着它的
`rm` 一起放行。

命令里的路径就是它点名的那些路径，变量也算：`cat $HOME/.ssh/id_rsa` 和
`cat ~/.ssh/id_rsa` 一样被拒绝；命令里的赋值后面的词看得见它
（`DIR=/etc cat $DIR/passwd`）。替换（`$(...)` 和反引号）也是一条命令：
`echo $(rm -rf ~)` 和 `rm -rf ~` 一样危险。

```bash
ls -la                       # 放行
git status                   # 放行
curl http://example.com      # 要问：把数据送出这台机器
pytest -q && rm -rf build    # 要问：rm 是危险的
cat /etc/passwd              # 拒绝
```

## 会话

- **新建、列出、续接、复制**——`--resume`、`--continue`、`--fork`、`--list`。
- **事件日志是唯一的事实**——每条消息、每次工具调用、每个结果、每笔钱都
  追加进一个 JSONL 文件。会话靠重放它重建。
- **被掐死的会话会修好**——结果没回来的那次工具调用会补上一个说明它没回来
  的结果，所以会话还能接着聊。`/rewind` 退回去把结果退掉了，也是这么修的。
- **检查点**——每次写文件之前存一份快照，`/rewind` 能退回去。
- **`/clear`**——开一个新会话，旧的留在日志里。
- **有名字、能收起来、也能删掉**——`/rename`、`/archive`、`/delete`。收起来的
  会话不在 `/resume` 的列表里，但它还在盘上。
- **历史可以留，也可以不留**——`history.persistence: save-none` 把会话留在
  内存里，`history.max_bytes` 在历史超过它的时候删掉最老的那些。正在跑的那个
  会话永远不在其中。
- **花了多少钱**——每个会话的 token 和花费，在状态栏、在 `/cost`、在
  追踪文件里。
- **没有价格的模型**——钱是不知道，不是零：状态栏、`/cost` 和会话列表显示的是
  `$?`。这种模型的预算是 `agent.token_limit`。
- **追踪**——`coder export --format json|otel` 把会话导出来，给看板或者
  OpenTelemetry 用。

### 会话的追踪

追踪就是事件日志加上这个会话的指标。`coder export` 把它写成文件，
`telemetry.otel_endpoint` 把它送给采集器：

```yaml
telemetry:
  otel_endpoint: "http://localhost:4318/v1/traces"
  otel_headers:
    authorization: "Bearer …"
```

- **一轮一个 span，一次模型调用一个 span，一次工具调用一个 span**——一轮里
  的那些调用是这一轮的子 span；
- **钱在 span 上**——`turn.cost`、`cost`、`tokens.in`、`tokens.out`；
- **每个 span 只发一次**，在这一轮结束的时候发；
- **后端不在只是句警告**——会话照常往下走，追踪下一轮再发一次；
- **事件日志仍然是唯一的事实**——追踪是从它算出来的，后端在不在，日志都写；
- **项目不能把追踪送到别处**——它只能关掉追踪（`otel_endpoint: ""`），
  不能指着自己的地址。

`coder export --format otel --push` 手动发一个会话。见
[追踪导出](coderagent_export.md)。

### 用法例子

```bash
coder -t "第一个任务"                     # 新会话
coder --list                              # 这个目录的会话
coder --resume 20261109-3f0a91 -t "接着说"  # 续上那个
coder --continue -t "接着说"                # 续上这个目录里最新的
coder --fork 20261109-3f0a91 -t "另一条路"  # 复制一份，原来那份不动
```

一个会话的文件都在 `~/.coderagent/` 里：

```
~/.coderagent/sessions/20261109-3f0a91.jsonl        # 事件日志
~/.coderagent/sessions/20261109-3f0a91.meta.json    # id、cwd、created_at、model_name
~/.coderagent/checkpoints/20261109-3f0a91.json       # 写文件前的快照
```

事件日志一行一个 JSON 对象，类型有 `user_message`、`assistant_message`、
`tool_call`、`tool_result`、`approval_request`、`approval_response`、
`state_change`、`compaction`、`reflection`、`verify`、`reverted_to`、`error`、
`turn_end`。

`/rewind` 只还原**文件**——命令对外部世界做过的事还是做过了——并把会话的
历史截断到快照那一刻。

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `ValueError: no checkpoint '<id>' in this session` | `/rewind` 拿到的 id 不是这个会话的检查点。 | 不带 id 的 `/rewind` 会列出检查点。 |
| `/resume <不存在的 id>` 起了一个目录是 `.` 的会话 | 日志里没有这个 id 不会报错，它会造一个空会话。 | 用 `coder --list` 看看有哪些 id。 |
| 一轮以 `stop_reason: max_turns` 结束 | agent 用了 100 次模型调用还没完（`agent.max_turns`）。`bypass` 模式下这个上限不拦。 | 调大 `agent.max_turns`，或者把任务拆小。 |
| agent 不出声就停了 | 这一轮被切断了：到了模型调用的上限、预算上限或者 token 上限。界面会在最后一条回答下面写明。 | 调大那一行里说的上限（`agent.max_turns` 之类），或者把任务拆小。 |
| 一轮以 `stop_reason: cost_exceeded` 结束 | 这一轮花的钱超过了 `agent.cost_limit`。`0` 是没有上限。`bypass` 模式下这个上限不拦。 | 调大 `agent.cost_limit`。 |
| 一轮以 `stop_reason: token_limit` 结束 | 这一轮用的 token 超过了 `agent.token_limit`。`0` 是没有上限。模型没有价格时钱不动，token 就是预算。`bypass` 模式下这个上限不拦。 | 调大 `agent.token_limit`。 |
| 一轮以 `stop_reason: error` 结束 | 模型调用重试完了还是失败。错误文本在 `error` 里。 | 看 `error`，那是厂商的消息。 |
| 一轮以 `stop_reason: interrupted` 结束 | 有人按了 `ctrl+c`。 | 会话已经存下来了，用 `--resume` 接着来。 |
| 追踪没有到后端 | 后端拒收了它，或者压根不在。原因在 agent 的日志里。 | 查一下 `telemetry.otel_endpoint` 和那几行头。 |

以 `cost_exceeded` 或 `error` 结束的一轮**不会**被沉淀成记忆：记忆里只留
失败之前学到的东西。

## 上下文

- **token 是数出来的**——装了 tiktoken 就精确数，没装就估。
- **窗口跟着模型走**——DeepSeek 64k、Claude 200k、GPT 128k 这样。配置文件
  里写了 `context_window` 就以它为准。
- **自动压缩**——对话到窗口的 80 % 就做摘要、把历史缩短。摘要是结构化的：
  目标、发现、决定、动过的文件、没解决的问题、下一步、见过的错。
- **留什么**——最近几轮，或者最近 40 % 的 token，哪个多留哪个。
- **`/compact`**——随时手动压缩。
- **`/recap`**——总结一下对话，但什么都不丢：总结是给你看的，模型看到的还是
  整段对话。
- **消息的顺序**——系统提示词、指令文件、todo、会话摘要，然后是历史。
- **指令文件会裁**——一个文件最多 32768 字节（`context.project_doc_max_bytes`）。
  太长的裁短，而且告诉 agent 它没看全。记忆文件同样裁。

### 用法例子

```yaml
context:
  context_window: 64000
  compact_threshold: 0.8
  keep_recent_turns: 20
  keep_recent_token_ratio: 0.4
  compact_every_turns: 40
  summarize_model: deepseek/deepseek-flash
```

配置里没有 `context_window` 时，窗口跟着模型名字走：`gpt-` 128k、`claude`
200k、`deepseek` 64k、`qwen` 32k、`llama` 8k、`gemini` 1M、`mistral` 32k、
`kimi` 256k、`minimax` 200k，别的都是 200k。

摘要是一个 JSON 对象，键是这些：

```json
{
  "goal": "fix the failing test in test_api.py",
  "findings": ["the timeout of the client is 5 seconds, the test needs 10"],
  "decisions": ["raise the timeout in the fixture"],
  "files_touched": ["tests/test_api.py"],
  "open_questions": [],
  "next_steps": ["run the suite again"],
  "errors_seen": ["TimeoutError after 5 seconds"]
}
```

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `... (nothing left to compact)` | 这一轮因为上下文太大而失败，而且已经没什么可缩的了。 | 调大 `context.context_window`，调小 `context.reserved_output`，或者 `/clear` 重来。 |
| 摘要是个兜底版本，不是真的摘要 | 模型没按摘要的 JSON 回答。试两次之后就用保守摘要：最后五条消息，`next_steps` 是 `["re-read the files that were mentioned to recover the details"]`。上一轮的摘要会合并进来，所以会话不会把记忆丢了。 | 不用管，会话继续走。再问模型一次那些细节。 |
| 摘要里没说改过哪些文件 | 模型没说它动过什么。文件列表从消息里取——消息才是事实。 | 不用管。 |
| `recent_errors` 是空的，但会话里明明有错 | 只有以 `Error:` 开头的工具消息会被收集，而且只留最后三条。 | 不用管。 |

token 的计数：装了 tiktoken 是精确的，没装是估的
`int(chars / 3.6) + 4 * len(messages)`。估小了会让压缩来晚一点，所以长会话
值得装 tiktoken。

## 记忆

- **项目记忆**——`.coderagent/memory`，一轮结束时把关于项目的东西写下来。
- **用户记忆**——`~/.coderagent/CLAUDE.md`，记用户的偏好。
- **偏好要等人确认**——先落在 `pending-memory.md`，`/memory confirm` 才写
  进去。
- **指令文件**——仓库和项目的 `AGENTS.md` 与 `CLAUDE.md`、用户的 `CLAUDE.md`，
  agent 都读。从子目录里启动，仓库根的规则照样读得到。
- **可以关掉**——`memory.enabled`。

### 用法例子

三个文件：

```
.coderagent/memory/projects.md        # agent 学到的关于项目的东西
.coderagent/pending-memory.md         # 等着被确认的偏好
~/.coderagent/CLAUDE.md                # 已经确认过的偏好
```

一轮结束时，agent 看最后 40 条消息，把学到的写下来：

```markdown
# Project memory

- the tests of the API are run with `pytest tests/`, they need a postgres on localhost
- the release is made with `bump2version`, not with a manual edit of setup.py
```

用户的偏好先进 `pending-memory.md`：

```markdown
# Preferences waiting for a confirmation

- always answer in Chinese
```

`/memory confirm` 之后才进 `~/.coderagent/CLAUDE.md`：

```markdown
## Preferences

- always answer in Chinese
```

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `The memory was not written: {path} would grow past 200 lines; tidy it up first.` | 那个文件会超过 200 行。 | 把文件写短一点，或者拆开。 |
| 日志里的警告 `The reflection of the session failed` | 模型没有按预期的 JSON 回答，所以什么都没写。会话本身没事。 | 不用管，下一轮会再试。 |
| `Wrote 2 preference(s) to /Users/you/.coderagent/CLAUDE.md.` | 确认成功了。 | — |
| `Nothing like that in the memory.` | `/memory forget` 没找到那段文字。 | 用 `/memory` 看看现在有什么。 |
| `Removed.` | `/memory forget` 把那段文字删了。 | — |

记忆可以整个关掉：

```yaml
memory:
  enabled: false
```

## 扩展

- **子 agent**——`.coderagent/agents/*.md`：名字、说明、系统提示词、工具
  清单、最大轮数。`code-explorer`、`verifier`、`refactorer` 是自带的。
  模型看得见它们的索引，能直接按名字调。
- **技能**——`.coderagent/skills/<名字>/SKILL.md`：某类任务的步骤、脚本和
  模板。合适的时候 agent 自己会载入。
- **插件**——`.coderagent/plugins`：一个 Python 模块，能加工具、命令和
  hook。第一次用要信任一次。
- **hook**——九个时机：`SessionStart`、`UserPromptSubmit`、`PreToolUse`、
  `PostToolUse`、`Stop`、`SessionEnd`、`PreCompact`、`PostCompact` 和
  `SubagentStop`。hook 是一条命令，读 JSON 答 JSON：
  允许、拒绝、拦下来，带理由、带额外上下文，或者带改写过的参数。
- **自己的命令**——`.coderagent/commands/*.md` 和
  `~/.coderagent/commands/*.md`：一个 slash 命令，带说明、
  参数提示、能用的工具，还有自己的模型。同名时项目里的那个算数。
- **命令的工具可以再收窄**——`allowed-tools: bash(git diff:*), read` 的意思是：
  这条命令能读、能跑 `git diff`，别的干不了。这个限制在哪种权限模式下都在。
- **MCP 服务器**——stdio。它们的工具和别的工具一样，工具名是
  `mcp__<服务器>__<工具>`，一样要审批，断了会自己重连。
- **项目里的代码要等一个决定**——项目定义的 MCP 服务器、hook 和验证命令都是
  没人问就跑起来的程序，所以先等用户决定：`/trust` 列出等着的东西，`/trust 1`
  信任其中一个。决定是记在命令上的：命令变了要重新信任。
- **项目只能拿走工具，不能给**——项目的模式只能是 `plan` 或 `readonly`，它的
  规则只能拒绝，它禁掉的路径是加在用户那些之上的，它列的工具只能从用户的工具
  里拿掉。它也不能挑那些要跑在用户机器上的程序：编辑器、通知程序、沙箱的环境
  都归用户决定。它也不能往 agent 的环境里塞变量，也不能抬高会话的上限。

### 用法例子

一个子 agent，`.coderagent/agents/scout.md`：

```markdown
---
name: scout
description: Finds the place where a feature is implemented
tools: read, grep, glob, ls
model_purpose: cheap
max_turns: 15
---

You look for code. You never change anything. You answer with the files and
the line numbers.
```

模型把它当工具调：

```json
{"tool": "task", "params": {"subagent_type": "scout", "description": "where is the auth?", "prompt": "find the auth code"}}
```

回答是一个 JSON 对象：

```json
{
  "status": "ok",
  "summary": "The auth is in src/auth/session.py.",
  "findings": ["src/auth/session.py:42 defines create_session"],
  "files_touched": [],
  "cost": 0.0004,
  "turns": 3,
  "purpose": "cheap"
}
```

一个技能，`.coderagent/skills/release/SKILL.md`：

```markdown
---
name: release
description: How to make a release of this project
---

1. Run the test suite.
2. Run `bump2version patch`.
3. Push the tag.
```

一个 hook，写在配置里：

```yaml
hooks:
  events:
    PreToolUse:
      - matcher: "bash"
        hooks:
          - type: command
            command: ./.coderagent/hooks/check_secrets.sh
            timeout: 10
            strict: false
```

hook 从 stdin 读 JSON，往 stdout 写 JSON：

```json
{"decision": "block", "reason": "the command writes a secret"}
```

`decision` 是 `allow`、`deny` 或 `block`；hook 还可以带 `additionalContext`，
或者用 `updatedInput` 改写这次调用。工具的 `updatedInput` 是一份参数映射；
`UserPromptSubmit` 的 `updatedInput` 是一个字符串，用来改写用户的提问。

一个自己的命令，`.coderagent/commands/commit.md`：

```markdown
---
description: Make a commit of the changes
argument-hint: [message]
allowed-tools: bash(git diff:*), read
model: cheap
---

Commit everything with the message: $ARGUMENTS
```

工具后面的模式也是一道限制：`bash(git diff:*)` 是说这条命令只能跑
`git diff`，别的命令都跑不了，用户的规则也不能把它放宽。没写出来的工具
就是没有。

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `Error: unknown sub agent 'scout'. Available sub agents: code-explorer, refactorer, verifier.` | 索引里没有这个子 agent。 | 用列出来的名字；自己写的那些在系统提示词的索引里。 |
| `Error: the sub agents are not available in this session.` | `task` 工具没注册——`tools.enabled` 被收窄了。 | 把 `task` 放回 `tools.enabled`。 |
| `Error: unknown skill 'release'. Available skills: {...}.` | 这个技能不存在。 | 技能是 `.coderagent/skills/<名字>/SKILL.md`。 |
| `Trusted 'x'. It is loaded the next time the agent starts.` | `/plugins trust x` 的回答。 | 下次起 agent 才会用上这个插件。 |
| `Error: the hook blocked 'bash'. the command writes a secret` | `PreToolUse` 的 hook 拒绝了这次调用。 | 改命令，或者改 hook。 |
| `Hook 'check_secrets.sh' timed out, ignoring it` | hook 跑得比它的超时久。调用放行。 | 调大 `timeout`，或者让 hook 快点。 |
| `Hook 'check_secrets.sh' failed with RuntimeError: ...` | hook 崩了。调用放行。 | 修 hook。加 `strict: true` 就会挡住调用。 |
| `Error: the MCP server 'echo' is not connected.` | 服务器没跑起来。 | 检查服务器的 `command` 或者 `url`；`/mcp` 里会写 `connected`、`failed: <错误>` 或者 `no command and no url`。 |
| `Error: the MCP tool 'echo' failed: RuntimeError: ...` | 服务器回的错。消息里的名字是服务器那边的名字。 | 服务器的消息就在答案里。 |

自己的命令在 `<cwd>/.coderagent/commands/*.md` 和 `~/.coderagent/commands/*.md`
里找——agent **不会**一层层往上找。同名时项目里的那个算数。

## 沙箱

- **默认是本机**——命令就在工作目录里跑。
- **也可以是容器**——`docker`、`singularity`、`bubblewrap`、`contree`，
  还有 SWE-rex 的远程沙箱。是随 mini-swe-agent 一起搬过来的那一批环境。
- **三档**——`sandbox.mode` 是 `full-access`（默认）、`workspace-write` 或者
  `read-only`。由**操作系统**来执行：macOS 上是 Seatbelt，Linux 上是 bubblewrap。
- **只有 `bash` 进沙箱**——文件工具还在工作目录里。`read-only` 那一档把它们也拒了。
- **`/sandbox`**——告诉你命令在哪里跑。

### 用法例子

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
```

一共有七种：`local`、`docker`、`singularity`、`bubblewrap`、`contree`、
`swerex_docker`、`swerex_modal`。环境不认识的选项会被忽略，所以一个文件里
可以同时写好几种环境的设置。

那一档属于本地的沙箱，和权限模式是**两条正交的轴**：权限那一层会问用户，
沙箱这一层谁都不问。

```yaml
sandbox:
  type: local
  mode: workspace-write
```

`/sandbox` 回答类型、那一档、生效的选项和在用的环境：

```
type: local
mode: workspace-write
environment: local/workspace-write
```

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `ValueError: Unknown environment type: nope (resolved to nope, available: {...})` | 类型不是那七种之一。 | 用上面列出的名字。 |
| `CalledProcessError: Command '[...]' returned non-zero exit status 1.` | 容器起不来，或者镜像拉不下来。 | 检查镜像名字，以及 docker 是不是在跑。 |
| `FileNotFoundError: [Errno 2] No such file or directory: 'singularity'` | 这个环境的二进制没装。 | 装上，或者换一个类型。 |
| `UnsupportedSandbox: The read-only mode needs bubblewrap (bwrap), which this machine does not have.` | 这台机器没有能建沙箱的程序。 | 装上 bubblewrap，或者用 `full-access`。 |
| 文件工具动到了宿主机的文件 | 只有 `bash` 进沙箱。 | 这是设计如此：`read`、`edit` 这些工具动的是会话的工作目录。 |

## 校验

- **默认不开**——不配 `verify.commands` 就什么都不查。
- **agent 必须把检查跑通**——模型想停下的时候命令会跑一遍；有一条没过，就把输出还给
  agent，让它接着改。
- **命令是你自己的，不是 agent 的**——所以它们按你的身份跑，不做权限检查，也不要审批。
- **轮数有限**——`verify.max_rounds`（默认 3）。轮数用完，这一轮就以
  `stop_reason: verify_failed` 结束。
- **结果进事件日志**——一条 `verify` 事件记着命令和没过的那几条。

### 命令什么时候跑

命令在 agent 想停的时候跑：它回答里没有工具调用的时候。它们不是每次工具调用之后
都跑，所以一个一直忙着的 agent 从来不会被检查。三道闸门的顺序是 `Stop` hook、
这些命令、然后是答案的 schema。

这些命令是**用户**的，不是 agent 的，所以它们：

- 不做权限检查——`permissions` 里的规则看不见它们，
- 不走 hook——不会为它们调用 `PreToolUse` 和 `PostToolUse`，
- 不要审批——没人被问，
- 不受 `sandbox.mode` 的限制——那一层只管到 `bash` 工具，这些命令直接进会话的环境。

它们跑在会话的环境里。`sandbox.type: local` 时是会话的工作目录；用容器时是环境的
工作目录，默认是 `/`，除非给环境配了别的。容器和 bubblewrap 仍然关着它们：那里
的边界是环境，不是 `sandbox.mode`。

项目里的校验命令跟项目里的其它代码一样，先等用户一个决定。没被信任的那条会从配置
里被摘掉，于是校验根本不会发生——而且没有任何提示。

### 轮数

`verify.max_rounds`（默认 3）是这些命令跑的次数。失败会告诉 agent，让它去修，所以
三轮意味着它被纠正两次；第三次还是不过，这一轮就以 `stop_reason: verify_failed`
结束，那段消息在 `error` 里。

命令是一个接一个全跑完的，没过的都会列出来。超时的命令算失败，退出码是 `-1`。

命令的输出回到模型之前会被裁到 2000 个 token：头尾留下，中间砍掉，中间放一行标记，
说明少了多少。

### 用法例子

```yaml
verify:
  commands:
    - python -m pytest -q
  max_rounds: 3
  timeout: 300
```

模型说做完了、而测试没过的时候，agent 会收到这样一段：

```
[verify] These commands did not pass. Fix the problem and try again.

$ python -m pytest -q
2 failed, 1 passed
[exit code 1]
```

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| 这一轮以 `stop_reason: verify_failed` 结束 | `verify.max_rounds` 轮用完了，命令还是没过。 | 在事件日志里看最后一轮的输出。 |
| 检查在沙箱里跑，但找不到文件 | 沙箱里没有会话的工作目录。 | 给环境配一个工作目录，或者用 `local`。 |
| 检查跑太久 | 命令超过 `verify.timeout` 秒被杀掉了。 | 调大 `verify.timeout`。 |
| agent 反复改同一处 | 检查要的东西 agent 做不到。 | 改检查，或者改任务。 |

## 终端界面

- **答案是流式出来的**——正文和思考过程都是。
- **状态栏**——模型、token、花费、目录、权限模式。
- **工具卡片**——这次调用、输出、以及这次改动的 diff。
- **审批**——`y`、`n`、`a`，或者方向键在带编号的列表上选。
- **长输出折起来**——有意思的那部分留在眼前。
- **todo 面板**——这一轮要做的事。
- **命令有自己的位置**——你敲的那一行和命令的回答各自是一条消息，agent 的回答
  还在。
- **输入框有历史**——`↑` 和 `↓` 翻你发过的消息，跟 shell 一样；翻过最新那条
  就回到你正在写的那句。
- **用 `@` 提文件**——敲 `@src/app` 会把文件的路径补全，`→` 收下这个补全。
- **会话面板**——`ctrl+o` 列出这个目录的会话，`enter` 接着选中的那个继续，
  `escape` 关掉面板。
- **文件树**——`ctrl+t` 在左边打开：用户开给 agent 的那些目录（`permissions.include_dirs`，
  一个都没开就是工作目录）里的文件，三层深，改过的有标记
  （`+` 新增、`●` 改过、`-` 删了、`?` 新文件）。点一个文件就把它的路径
  填进输入框。
- **一轮结束时通知终端**——通知里带着 agent 的回答，长的一轮不会错过。
  `ui.notifications: false` 可以关掉。
- **也可以用你自己的程序通知**——`ui.notify_command` 写一个程序名，它会拿到
  通知的标题和正文两个参数（比如 `notify-send`）。程序跑不起来只是记一条警告，
  不会弄坏会话。**项目不能挑通知程序**：那个程序跑在用户的机器上。
- **答案是 Markdown**——代码块、表格、列表长得跟项目 README 里一样。文字流出来
  的时候是纯文本，说完了才渲染；`ui.markdown: false` 可以让它一直是纯文本。
- **可以发图片**——`/image shot.png 这是什么` 把图片和这句话一起发过去。发之前
  agent 会先问模型看不看得图：看不懂的模型也会照样回答，而且答案是编的。
  `model.capabilities` 写模型能吃什么，给 litellm 不认识的那些模型用。
- **文件在你的编辑器里打开**——`/open src/app.py` 用 `ui.file_opener` 指定的
  程序打开它（`vscode`、`cursor`、`windsurf`，或者你自己的命令）。
  **项目不能挑编辑器**。
- **`ctrl+c` 能停掉正在跑的工具**——不只是这一轮：shell 里跑着的命令会被停掉，
  它自己起的那些进程也一样。它也能把模型正在写的回答截断：这一轮在模型还在
  写的时候就结束，写了一半的那段不留下来。

### 用法例子

状态栏长这样：

```
deepseek/deepseek-flash | 1.5k/64k | $0.0000 | ~/work/project | default
```

审批是一个带编号的列表，选中的那个有标记：

```
1 [*] y allow
2 [-] n deny
3 [-] a always allow
```

`←`/`→` 移动光标，`↑`/`↓` 也一样，数字键直接跳到那一行，空格切换多选，
`enter` 确认，`y`、`n`、`a` 直接回答。`ctrl+c` 打断这一轮，`ctrl+q` 收尾
会话并退出，`ctrl+o` 打开会话面板，`ctrl+t` 打开文件树。

todo 面板用 `◉`（完成）、`◐`（进行中）、`○`（待办）标记任务状态。

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| 工具要审批时界面没反应 | 没有终端——这次运行是无头的。 | 这次调用会被拒。用 `--permission-mode bypass` 或者写条规则。 |
| 工具输出下面有 `▸ 42 more lines` | 输出比卡片长。 | 有意思的部分还在眼前；要全文就打开文件，或者把命令的输出调少再跑一次。 |
| 界面起不来 | 终端里不给任务的 `coder` 会起界面；没有终端就打印 `no task given`。 | 用 `coder --tui` 强制起。 |
| `The agent is working. Wait for it, or press ctrl+c to stop it.` | agent 还在这一轮的中途时敲了命令，命令没有跑。 | 等这一轮结束，或者按 `ctrl+c` 把 agent 停掉。 |
| `shot.png is too big: 7000 KB, the limit is 5120 KB` | 图片超过了 5 MB 的上限。 | 把图片弄小一点，或者当成文件让 agent 自己去读。 |

## 网页版

- **聊天页**——三栏：左边是会话和文件，中间是对话，右边是状态、改动和
  文件。
- **答案是流式到的**——走 SSE，中途才打开页面的浏览器看到的是整段回答。
- **设置页**——模型写成表单：模型名、接口地址、API key、最多重试；其余的模型
  设置写在配置文件里。
- **连通性测试**——只在 API 里（`POST /api/config/model/test`）：发一次最便宜
  的调用，顺带告诉模型会不会调工具。
- **权限在两个地方**——设置页管下一个会话，聊天页管当前这个会话，立刻生效。
- **浏览器里也有审批**——同样三个答案。
- **浏览器里也能发图**——输入框旁边的「+」按钮，或者直接粘进去。图跟消息
  一起进模型，类型和上限跟终端的 `/image` 一样。
- **语言**——英文和中文。顶栏的下拉框换语言时整个页面当场换掉，不刷新，
  选择记在浏览器和 cookie 里；访客没选过的时候由地址所在的地区决定。
- **安全模型**——没有认证，默认只听 `127.0.0.1`，写接口要一个跨站请求
  发不出来的头，路径出不了工作目录，key 只在你要的时候才露面。

### 用法例子

```bash
coder web --cwd . --port 8765
```

```
coder web: http://127.0.0.1:8765
```

接口就是普通 HTTP。给会话发一条消息：

```bash
curl -X POST http://127.0.0.1:8765/api/sessions/20261109-3f0a91/messages \
  -H 'X-Coder-Client: 1' -H 'Content-Type: application/json' \
  -d '{"text": "run the tests"}'
```

订阅会话的事件流：

```bash
curl -N http://127.0.0.1:8765/api/sessions/20261109-3f0a91/stream
```

接口一览：

| 接口 | 干什么 |
|---|---|
| `GET /api/sessions` | 工作目录里的会话 |
| `POST /api/sessions` | 新建会话 |
| `GET /api/sessions/{id}` | 一个会话 |
| `GET /api/sessions/{id}/events` | 会话的事件 |
| `GET /api/sessions/{id}/items` | 某个序号之后的条目 |
| `GET /api/sessions/{id}/stream` | 事件流（SSE） |
| `GET /api/sessions/{id}/status` | 状态、模型、token、花费 |
| `GET /api/sessions/{id}/metrics` | 会话的指标 |
| `GET /api/sessions/{id}/changes` | 改动过的文件 |
| `POST /api/sessions/{id}/resume` | 续接会话 |
| `POST /api/sessions/{id}/fork` | 复制会话 |
| `POST /api/sessions/{id}/messages` | 发消息 |
| `POST /api/sessions/{id}/review` | 评审这个项目的改动 |
| `POST /api/sessions/{id}/interrupt` | 打断这一轮 |
| `POST /api/sessions/{id}/mode` | 改这个会话的权限模式 |
| `POST /api/approvals/{id}` | 回答审批 |
| `GET /api/commands` | slash 命令 |
| `GET /api/config` | 配置和它的层 |
| `PUT /api/config/model` | 把模型写进用户级文件 |
| `GET /api/config/model/key` | 端点的 key |
| `PUT /api/config/permissions` | 把权限写进用户级文件 |
| `POST /api/config/model/test` | 一次最便宜的调用，测模型 |
| `GET /api/files` | 工作目录里的文件 |
| `GET /api/file` | 一个文件 |
| `GET /api/diff` | 一个文件的 diff |
| `GET /api/i18n/{language}` | 一种语言的文案 |

### 出错时怎么办

| 状态码 | 消息 | 什么意思 | 怎么办 |
|---|---|---|---|
| 403 | `the X-Coder-Client header is missing` | 写操作没带那个头。别的站点的浏览器发不出这个头。 | 加上 `-H 'X-Coder-Client: 1'`。 |
| 404 | `there is no session with the id {id}` | id 不存在。 | `GET /api/sessions` 看列表。 |
| 404 | `no approval is waiting for the id {id}` | 这个审批已经答过了，或者它超时了。 | 不用管。 |
| 404 | `unknown language` | `/api/i18n/{language}` 的语言没上线。 | 用 `en` 或 `zh`。 |
| 400 | `the message is empty` | 消息没有内容。 | 给点文字。 |
| 400 | `unknown permission mode '{value}'` | 模式不是那五个之一。 | 用 `default`、`acceptEdits`、`plan`、`readonly` 或 `bypass`。 |
| 400 | `the decision must be allow, deny or always` | 审批的回答不对。 | 用 `allow`、`deny` 或 `always`。 |
| 400 | `'{path}' is not a directory` | 文件接口的路径是个文件。 | 换成目录。 |
| 403 | `'{path}' is outside the working directory {cwd}` | 路径走出了工作目录。 | 没有办法——这就是边界。 |
| 409 | `the session {id} is running` | 会话正忙着，不能复制或续接。 | 等这一轮结束，或者打断它。 |

没人回答的审批在 `ui.approval_timeout` 秒之后被拒，浏览器会收到
`timed_out: true`。

批准一个会改文件的工具，会往 `~/.coderagent/rules.yaml` 写一条规则——和
终端用的是同一个文件。

服务起来时会把地址打出来。用 `--host 0.0.0.0` 时它会警告：

```
The web interface listens on 0.0.0.0: everybody who can reach that address can drive the agent.
```

## 配置

- **五层**——包里的默认值、项目文件 `.coderagent/config.yaml`、用户文件
  `~/.coderagent/config.yaml`、生效的 profile、命令行的覆盖（`-c key=value`）。
  后面的赢。
- **有哪些段**——`model`、`agent`、`tools`、`permissions`、`context`、
  `memory`、`checkpoint`、`mcp`、`hooks`、`ui`、`sandbox`、`verify`、`telemetry`、
  `shell_environment`、`history`，还有 `profiles` 和 `profile`。
- **路径**——`MSWEA_CODER_HOME` 可以把用户级文件挪到别处。
- **设置页只写用户级文件**——项目级那份在仓库里，永远不写。

### 用法例子

```bash
# 一个文件。
coder -t "..." -c myconf.yaml
# 覆盖，可以给多次。
coder -t "..." -c model.model_name=deepseek/deepseek-chat -c agent.max_turns=20
```

五层，从低到高：

1. 包里的默认值（`src/coderagent/config/defaults.yaml`），
2. 项目的 `.coderagent/config.yaml`，
3. 用户的 `~/.coderagent/config.yaml`，
4. 生效的 profile，
5. 命令行的 `-c`。

模型名按这个顺序找：命令行的 `-c`、生效的 profile、用户文件、
`$MSWEA_MODEL_NAME`，最后是 `anthropic/claude-sonnet-4-5`。
**项目不能挑模型**：项目的 `model` 整段被丢掉——项目的端点会把整段对话，
连同用户的 key，一起送到别处去。
另外两处写了模型名字的地方也一样：项目的 `context.summarize_model` 被丢掉，
项目里的命令不许写 `model`。

**项目不能往 agent 的环境里塞变量**：项目的 `shell_environment.set` 被丢掉——
项目自己的 `LD_PRELOAD` 或 `PATH` 会把仓库里的代码带进用户机器上 agent 跑的
每一条命令里。项目也不能声称比模型更大的上下文窗口。**会话的上限**——
`agent.max_turns`、`agent.cost_limit`、`agent.token_limit`、
`agent.subagent_max_turns`、`agent.subagent_max_parallel`、
`tools.bash_timeout` 和 `tools.max_output_tokens`——项目只能**往下压**：
更大的那个换回默认值。你自己写下的上限是你自己的，用户文件、profile 和
命令行都压过项目。

### profile（命名配置）

profile 是一段有名字的配置，用 `--profile`（短写 `-p`）选它。它压在用户文件
上面，在命令行的 `-c` 下面：

```yaml
# ~/.coderagent/config.yaml
profiles:
  fast:
    model:
      model_name: deepseek/deepseek-chat
    agent:
      max_turns: 20
  careful:
    permissions:
      mode: plan
    verify:
      commands: ["pytest -q"]
```

```bash
coder -t "..." --profile fast
coder -t "..." -p careful
```

profile 的名字也可以写在配置里：

```yaml
profile: fast
```

**项目**既不许定义 profile，也不许选 profile：项目的 profile 会被丢掉，
跟仓库里带来的其它代码一样。选哪套权限是用户的决定。

项目的收紧仍然最要紧：项目把沙箱关上了（`sandbox.mode: read-only`），
那它就是关着的，profile 写 `full-access` 也一样。项目也不能决定命令**在哪里**跑：
沙箱的 `type` 和环境的那些选项都会从项目的配置里被丢掉。

各段和它们的键：

| 段 | 键 |
|---|---|
| `model` | `model_name`、`api_key`、`api_base`、`model_kwargs`、`max_retries`、`litellm_config`、`routing`、`routing_rules`、`set_cache_control`、`reasoning_effort`、`verbosity`、`review_model`、`capabilities` |
| `agent` | `system_prompt`、`max_turns`、`cost_limit`、`token_limit`、`subagent_max_turns`、`subagent_max_parallel` |
| `tools` | `enabled`、`disabled`、`bash_timeout`、`max_output_tokens`、`schema_budget_tokens` |
| `permissions` | `mode`、`rules`、`deny_paths`、`include_dirs`、`network` |
| `context` | `context_window`、`reserved_output`、`compact_threshold`、`keep_recent_turns`、`keep_recent_token_ratio`、`compact_every_turns`、`auto_compact`、`summarize_model`、`summary_chunk_tokens`、`project_doc_max_bytes` |
| `memory` | `project_path`、`user_path`、`enabled` |
| `checkpoint` | `enabled`、`keep` |
| `mcp` | `servers`、`timeout` |
| `hooks` | `events` |
| `ui` | `approval_timeout`、`notifications`、`notify_command`、`markdown`、`file_opener` |
| `shell_environment` | `inherit`、`exclude`、`include`、`set` |
| `sandbox` | `type`、`mode` 和环境的那些选项 |
| `verify` | `commands`、`max_rounds`、`timeout` |
| `telemetry` | `otel_endpoint`、`otel_headers`、`otel_timeout` |
| `history` | `persistence`、`max_bytes` |
| `profiles` | 有名字的几段配置，`--profile` 从里面挑一个 |
| `profile` | 生效的那个 profile 的名字 |

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| 什么都没发生，设置被忽略了 | 不存在的键会被静默忽略。 | 按上面的表核对拼写。 |
| `yaml.scanner.ScannerError` | 某一层的 YAML 解析不了。 | 修 YAML，消息里带着行号。 |
| `pydantic_core.ValidationError` | 值的类型不对——该是数字的地方写了字符串。 | 消息里说了是哪个字段。 |
| `FileNotFoundError: Could not find config file for ... (tried: [...])` | 给了 `-c myconf.yml`，但找的是 `myconf.yaml`。 | 用带 `.yaml` 的名字，或者给全路径。 |
| 模型不是文件里写的那一个 | 上面的一层赢了。 | 记住顺序；设置页上有各层的列表。 |
| `ValueError: unknown profile 'slow'. Use one of: fast, careful.` | profile 的名字不在配置的 `profiles` 里。 | 检查拼写，或者把 profile 加进文件。 |

## 命令

三十五个内置命令：`/help`、`/model`、`/mode`、`/plan`、`/compact`、`/recap`、
`/side`、`/clear`、`/resume`、`/fork`、`/rename`、`/archive`、`/delete`、`/rewind`、`/diff`、
`/review`、`/image`、`/mention`、`/open`、`/init`、
`/cost`、`/todos`、`/mcp`、`/permissions`、`/hooks`、`/agents`、`/skills`、
`/plugins`、`/trust`、`/memory`、`/status`、`/sandbox`、`/export`、`/context`、
`/exit`（别名 `/quit`）。

自己的命令放在 `.coderagent/commands/*.md` 和 `~/.coderagent/commands/*.md`，
和它们一起用。

`/help` 会说每个命令收什么——`/mode` 的那几个模式、`/trust` 的编号、自己命令的
参数——不用记。

### 审查

`/review` 把 diff 交给模型，让它说改动里哪里有问题。不带范围时审的是工作区里的
改动，带范围时（`/review main..HEAD`）审的是那个范围。新加的、还没进版本库的文件
会在提示词里点名，模型觉得重要就自己去读。diff 超过 60000 字符会被截断，并且
告诉模型自己读文件。

审查是当前会话里的一轮，用的是它自己的提示词，提示词里明写不改任何文件。
结果留在对话里。

审查可以跑在另一个模型上：`model.review_model` 写它的名字，`model.routing.review`
压过它。两个都没写就还是会话自己的模型。这一轮的用途写在日志里，以后能翻出来。

### 总结，和岔开的对话

`/recap` 把到现在的对话总结一遍，把总结给你看：目标、发现、决定、动过的文件、
还没解决的问题、下一步。什么都不会被丢掉，也不会被压缩，总结本身也不进模型的
上下文——模型看到的还是整段对话。这是一份给你看的报告。总结要花一次模型调用，
这笔钱记在会话上，用途是 `recap`。

`/side <问题>` 在一段自己的对话里问问题。那段对话是当前会话的一份拷贝，有自己的
日志：问题和回答记在当前会话里，所以 agent 不会丢掉干活的线索，但也只有这些。岔开的
那段对话用的工具算在岔开的会话上，它花的钱记在当前会话上，用途是 `side`。

### 你提到的文件

提问里点名的文件会**带着内容**进消息，模型不用再花一次工具调用去读它：

```
看看 @src/app.py 做了什么
```

终端界面和命令行里都一样。`/mention` 是同一个意思，只是把路径写全：

```
/mention src/app.py 这个文件做什么
```

不存在的文件就当没写：`@` 还有别的用处（邮箱、装饰器），所以只有真的存在的
文件才会被打开。

**边界照样管着**：工作目录外面的文件、权限规则拒绝的文件，都不进消息。
消息里写的是「agent 读不了这个文件」，而不是把内容偷偷塞进去。

只带文本：不是文本的文件只会被点名，不会进去；图片走 `/image`。超过 20000
字符的文件会被截断，并且说明截断了。

文件里的密钥在内容进去之前就被换掉：跟工具输出一个规矩，所以被提到的文件里
有 key，也不会进会话日志。

### 用法例子

```bash
coder -t "/cost"          # 终端里跑一个命令
coder -t "/model deepseek/deepseek-chat"
coder -t "/mode plan"
```

带参数的命令，参数是这一行的剩下的部分：

```
/model deepseek/deepseek-chat
/rewind 20261109-3f0a91
```

终端界面里，命令是它自己的一条消息：你敲的那一行会显示出来，命令的回答不会顶掉
agent 的回答。agent 正在干活的时候敲命令会被拒绝。

浏览器里，命令在聊天页的命令面板里，列表来自 `GET /api/commands`。

### 出错时怎么办

| 你看到的 | 什么意思 | 怎么办 |
|---|---|---|
| `Unknown command '/foo'. Try /help.` | 没有这个命令。 | `/help` 看列表，`/help <名字>` 看某一个。 |
| `Unknown mode 'bogus'. Use one of: default, acceptEdits, plan, bypass, readonly.` | `/mode` 给了一个不存在的模式。会话的模式没变。 | 用那五个之一。 |
| `/rewind` 拿到的 id 不是检查点 | `ValueError: no checkpoint '<id>' in this session` | 不带 id 的 `/rewind` 会列出检查点。 |
| `Not a git repository: {cwd}` | `/diff` 跑的是 `git diff`，而这个目录不是仓库。 | 在仓库里跑，或者看网页版的改动。 |
| `No changes to review.` | `/review` 在工作区里没找到可审的东西。 | 先改点东西，或者给个范围：`/review main..HEAD`。 |
| `Git does not know '{revision}'` | `/review` 拿到的范围 git 不认。 | 用 `git log --oneline` 看看范围。 |
| `{path} already exists.` | `/init` 不会覆盖已有的 `AGENTS.md`。 | 自己改那个文件。 |
| `No sessions yet.` | `/resume` 不带 id 时，这个目录里什么都没有。 | 先跑一轮。 |

## 细节在哪

| 文档 | 里面有什么 |
|---|---|
| [coding agent 概览](coderagent.md) | 从第一次会话到所有文件，全套 |
| [命令](coderagent_commands_zh.md) | 每个命令，以及自己的命令 |
| [网页版](coderagent_web_zh.md) | 聊天页、设置页、API |
| [子 agent](coderagent_subagents_zh.md) | 怎么写一个子 agent |
| [技能](coderagent_skills.md) | 怎么写一个技能 |
| [hook](coderagent_hooks_zh.md) | 九个时机和 hook 的回答 |
| [插件](coderagent_plugins.md) | 怎么写一个插件 |
| [MCP 服务器](coderagent_mcp.md) | 服务器怎么配 |
| [记忆](coderagent_memory.md) | 那些文件和确认 |
| [模型路由](coderagent_routing.md) | 用途和规则 |
| [沙箱](coderagent_sandbox_zh.md) | 那些环境和那三档 |
| [追踪导出](coderagent_export.md) | 一个会话的追踪 |
| [快速开始](coderagent_quickstart.md) | 头十分钟 |
