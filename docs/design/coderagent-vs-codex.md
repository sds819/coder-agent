# 对照 Codex：coderagent 还差什么

> 这份文档把 coderagent 和 OpenAI Codex CLI 放在一起比，列出**还值得改进的地方**，
> 每一条都指到 coderagent 的具体文件，并标注工作量。
>
> 它不是路线图，也不是许愿单——是**一次对照审计的结论**：2026-11-16 读完 Codex 的
> 文档（sandbox / approval / 命令集 / 多模态那几页）和 coderagent 的源码之后，
> 把两边摆在一起得出的差集。
>
> 相关文档：[主架构](coding-agent-architecture.md)（能力差距矩阵那一节是本文的来源）、
> [设计逻辑](coderagent-design-logic.md)、[答问录](coderagent-answers.md)。

---

## 1. 一句话结论

> **coderagent 的「内核」比 Codex 强**（事件日志、信任边界、离线评测、网页版），
> **「外壳」比 Codex 弱**（沙箱隔离、命令覆盖面、界面细节）。

Codex 赢在**工程化的外壳**：OS 级沙箱、网络开关、四十多条 slash 命令、图像/音频输入、
可调整的分栏 UI、终端通知。coderagent 赢在**内核的可审计性**：所有副作用过同一道闸、
项目配置只能拿走能力不能给能力、事件日志是唯一事实来源、有一套能跑指纹对比的离线评测。

所以这份清单里，**真正该抄的是安全边界和输入通道**（P0 的 1、3、4、5 和 P1 的 1、2），
其余多半是「有了更好」而不是「缺了就危险」。

**进度**：§8 的第 1～7 步已经做完（两个 bug、网络开关、`/review`、`reasoning_effort`、
TUI 小件、死配置清理、OS 级沙箱），剩下的是第 8 步：图片输入、中断粒度、Markdown。
做完的条目在小节标题上标着「✅ 已修」，原样保留着原来的描述，好回头看差在哪。

---

## 2. 怎么读这份清单

| 级别 | 含义 |
|---|---|
| **P0** | 缺了会**不安全**或者**会出错**，先做 |
| **P1** | 缺了**明显不好用**，影响日常效率 |
| **P2** | 缺了**锦上添花**，或者只是**清理**（死配置、无效代码） |

工作量的口径：一个「小」= 半天以内，一个「中」= 一到三天，一个「大」= 一周以上。

---

## 3. P0：先做

### 3.1 没有 OS 级沙箱，网络也没有开关 ✅ 已修

**现状**：`sandbox.type` 默认 `local`（`src/coderagent/config/defaults.yaml:62`），
走 `build_environment()` → `CodingEnvironment`（`src/coderagent/core/sandbox.py:26-29`），
命令用 `subprocess` **以用户本人的身份**跑。想隔离只能整个换环境：

```yaml
sandbox:
  type: swerex_docker   # 或 bubblewrap / contree / modal
```

但这条路是**全有全无**的：要么整个 agent 在容器里，要么全在宿主上。Codex 的模型是
**两个正交的轴**——`sandbox_mode`（read-only / workspace-write / danger-full-access）
× `approval_policy`（on-request / on-failure / never），而且沙箱是**操作系统级别**的：

| 平台 | Codex 的隔离手段 |
|---|---|
| macOS | Seatbelt (`sandbox-exec`) |
| Linux | bubblewrap + seccomp + Landlock |
| Windows | 原生 sandbox |

而且 **Codex 默认断网**，agent 想联网得显式开。

**coderagent 现状**：

- ~~没有操作系统级的文件/进程约束，`local` 就是裸的 `subprocess`；~~ ✅ 已修
- `curl` / `wget` / `nc` 这些出网命令，在 `src/coderagent/tools/bash_policy.py:90-96`
  里被标成「危险」，但**危险只意味着弹审批框，不意味着拦下来**——
  `default` 模式下用户一路点「允许」就能把数据发出去；
- ~~没有 `sandbox_policy.network_access` 这样的开关。~~ ✅ 已修（见下面「已修」）

**影响**：~~一个被 prompt injection 拐走的 agent，在 `local` 模式下能读 `~/.ssh`、
能改 `~/.zshrc`、能把仓库内容 POST 到外面。`permissions.include_dirs` 只能**加**目录，
没有「只允许写这些目录」的方向。~~ ✅ 已修（网络开关 + OS 级沙箱）

**建议**：

1. ~~先做**便宜的半个**——加一个 `network: deny | allow` 开关，在 `bash_policy` 里把
   出网命令从「弹审批」升级成「直接拒绝」。~~ ✅ 已修（见下面）
2. ~~再做 `sandbox_mode` 三档，把 `local` 拆成 `read-only` / `workspace-write` /
   `full-access`，其中 `workspace-write` 在 macOS 上接 Seatbelt、Linux 上接 bubblewrap。~~ ✅ 已修（见下面）

**已修：网络开关**（`permissions.network`，默认 `allow`）

- `bash_policy.py` 里加了一张出网命令的表（`NETWORK_COMMANDS`）和 `git` 的出网子命令
  （`NETWORK_SUBCOMMANDS`），另有一个 `needs_network()` 判断某一段命令要不要出网；
- `PermissionPolicy` 多了一个 `network` 参数：`deny` 时，出网的命令**直接拒绝**，
  不是弹审批框；
- **拒绝在所有模式下都成立，`bypass` 也不例外**——这一点和原文写的
  「（`bypass` 模式除外）」不同：磁盘边界（`within_bounds()`）本来就在 `bypass`
  下成立，Codex 的 `network_access` 也和 `approval_policy` 是两个正交的轴，
  所以让网络边界跟磁盘边界一个口径；
- 用户写的 `allow` 规则**放宽不了**它，和路径边界一个待遇；
- 模型会被告知：一段 `<permission_network policy="deny">` 进上下文，和
  `<permission_mode ...>` 一样，每轮重算，不烤进 system prompt；
- 信任边界照旧：项目里的配置**只能关网络，不能开网络**（`core/trust.py` 的
  `tightened()` 把 `network` 留在配置里当且仅当它是 `deny`；`config/loader.py`
  里项目层说 `deny` 时，用户层不能把它重新打开）。

**已修：OS 级沙箱**（`sandbox.mode`，默认 `full-access`）

- 新模块 `src/coderagent/core/os_sandbox.py`：三档 `read-only` / `workspace-write` /
  `full-access`，由**操作系统**来执行——macOS 是 Seatbelt（`sandbox-exec`），
  Linux 是 bubblewrap（`bwrap`）。越界的命令是被**内核**挡下来的，不是被文件里的
  一条规则挡下来的；
- 配置上就是 `sandbox.mode`，只对本地沙箱有意义：

  ```yaml
  sandbox:
    type: local
    mode: workspace-write
  ```

- **命令是被包起来送进沙箱的**（`<tool> … /bin/sh -c '<整条命令>'`）：整条命令作为
  **一个参数**进去，所以解析管道的那个 shell 也在沙箱里——否则管道会有一半漏在外面；
- **约束的是 agent，不是用户**：围栏挂在 `ToolContext.sandbox` 上，只由 `bash` 工具
  的命令用。校验命令是用户自己的命令，按用户的身份跑，在沙箱外面；
- **`read-only` 连写文件的工具一起拒**（`write`、`edit`、`multi_edit`）：它们写的是
  用户机器上的文件，在沙箱外面，用户写的 `allow` 规则也放宽不了；
- **路径边界没有被绕开**：`within_bounds()` 在所有模式下都生效，还是用户的 `allow`
  规则放宽不了——这一点在原文里被点名过，实现时照做了；
- **闸和沙箱是两层，不是二选一**：`bypass` 跳过的是审批提问，不是磁盘边界；
- **可写的目录**：工作目录 + `permissions.include_dirs` + 系统的临时目录（构建总得
  有地方放东西），`read-only` 只留临时目录；
- **网络在操作系统那一层也关着**：`permissions.network: deny` 时，Seatbelt 加
  `(deny network*)`，bubblewrap 加 `--unshare-net`；
- **信任边界照旧**：项目里的配置**只能关沙箱，不能开沙箱**（`core/trust.py` 的
  `tightened()` 只留下更紧的那两档；`config/loader.py` 里两档里更紧的算数，
  用户层不能把项目关掉的沙箱重新打开）；
- **模型会被告知**：一段 `<sandbox mode="…">` 进上下文，每轮重算，不烤进 system prompt；
- **机器上缺那个程序，会话就起不来**（`UnsupportedSandbox`）：承诺兑现不了，就不要许。

**注意**：`within_bounds()`（`src/coderagent/tools/permissions.py`）在**所有**模式下都生效，
用户写的 `allow` 规则**放宽不了**这个边界——这是 coderagent 比 Codex 强的地方，
做 OS 级沙箱时不要把它绕开——**没有绕开**：`sandbox.mode` 的每一档都跑在
`within_bounds()` 后面，用户规则放宽不了它。

---

### 3.2 没有 `/review` ✅ 已修

**原来**：coderagent 的命令注册表在 `src/coderagent/ui/commands/builtin.py`，
二十来条命令里**没有 `review`**。Codex 有 `/review`，能把当前分支的改动拉出来做一次
专门的审查轮。

**影响**：审查这件事只能靠用户自己在输入框里写「帮我 review 一下这些改动」，
走的是普通对话路径——没有独立的提示词、没有独立的 diff 上下文。

**已修：一条 `/review [范围]` 命令**（`src/coderagent/ui/commands/review.py`）

- 不带范围时审查**工作树**的改动（`git diff HEAD`，没有提交时退回 `git diff`）；
  带范围时审查那个范围（`git diff main..HEAD`）；
- 范围 git 不认时说一句「Git does not know …」，不静默；
- **新增但还没进版本库的文件单独列出来**（`git status --porcelain`），它们不在 diff 里，
  提示词里点名，模型自己去读；
- diff 进的是**一次专门的审查轮**的提示词（`REVIEW_PROMPT`），提示词里明写
  「**Do not change any file**: this is a review, not a fix」——
  审查只出结论，不动代码（要改的话走正常的审批门）；
- diff 超过 60000 字符会被截断，并告诉模型「the diff is cut here, read the files yourself」；
- 审查轮在**当前会话**里跑，结果留在对话里，用户可以接着说「把第二条改掉」。

**实现要点**：命令自己不跑模型，它把提示词交给界面的 `submit` 回调——
`CommandContext` 多了一个 `submit` 字段（TUI → 工作线程，网页版 → 会话线程，
CLI → `render(loop.run_turn(...))`）。界面不能跑轮时（`submit is None`）说一句
「This interface cannot run a turn, so it cannot review.」就完了。
**没有**另起一个子 agent：审查留在对话里，用户能直接接着用结论。


---

### 3.3 没有 `reasoning_effort`（思考预算） ✅ 已修

**原来**：`src/coderagent/config/schema.py` 的 `ModelConfig` 里**没有** `reasoning_effort`
这个字段（grep 全仓为零）。传给 litellm 的是 `model_kwargs` 的其余部分，所以理论上
用户可以自己在 `model_kwargs` 里塞 `reasoning_effort: high`——但**没有开关、没有校验、
没有文档、没有界面**，而且**各个厂商对这个参数的叫法不一样**（OpenAI 是
`reasoning_effort`，Anthropic 是 `thinking.budget_tokens`，DeepSeek 是别的）。

**影响**：想省钱的用户没法「这个任务认真想」，想快点的用户也没法「别想了」。
`model.routing` 和 `model.routing_rules`（按用途选模型）能解决一部分，
但「同一个模型、不同的思考量」这个维度是空的。

**已修：一个 `model.reasoning_effort` 字段**

- 配置里写 `model.reasoning_effort: high`，取值是 `minimal` / `low` / `medium` / `high`，
  留空 = 模型的默认。**写错在加载配置时就被拒**（pydantic 的字段校验器），
  不用等到发请求才炸。
- 翻译在**一处**做：`src/coderagent/models/reasoning.py` 的 `translate(model_name, effort)`。
  OpenAI 这一家原样传 `reasoning_effort`；Anthropic 这一家换成
  `thinking: {type: enabled, budget_tokens: N}`（N = 1024 / 2048 / 8192 / 16384，
  Anthropic 至少要 1024 个 token，所以 `minimal` 就是 1024）。
- 翻译发生在 **`LiteLLMBackend` 里面**，在别名解析**之后**——`litellm_config` 里的别名
  指向的是哪个模型，就按那个模型的厂商来翻译。
- 用户自己在 `model_kwargs` 里写的同一个参数**优先**（`setdefault`），
  想手工调 token 数的人不受打扰。
- 因为翻译在 backend 里，**每一处**建 backend 的地方都白拿：主模型、`model.routing`
  的子模型、`/model` 换模型、网页版的连接测试、自定义命令。
- 界面上也有：网页版设置页的模型表单里多了一个「思考预算」下拉框；
  `/model` 会把当前的档位打印出来，换模型时**带着走**。

---

### 3.4 真 bug：`~/.coderagent/CLAUDE.md` 被加载了两次 ✅ 已修

**原来**：

- `src/coderagent/core/instructions.py:39` — `load_instructions()` 读
  `home / USER_FILE`，`USER_FILE = "CLAUDE.md"`（`instructions.py:13`），
  于是读的是 `~/.coderagent/CLAUDE.md`；
- `src/coderagent/core/memory.py:32` — `load_user_memory()` 读
  `home / Path(config.user_path).name`，而 `user_path` 的默认值就是
  `~/.coderagent/CLAUDE.md`（`src/coderagent/config/schema.py:108`）；
- 这两块在 `src/coderagent/core/context.py:215-220` 被**同时**拼进指令段。

**影响**：用户级的 `CLAUDE.md` 每次组消息都**出现两遍**，白烧 token；
更要紧的是，如果用户在这份文件里写了「每次回答都要先说 X」这类自我约束，
模型看到的是两遍，可能误以为那是强调。

**怎么修的**：`core/instructions.py` 加了 `once_per_file()`，组消息的时候
**一个文件只出一段**，后读的盖住先读的。记忆那份赢——它每轮重读，
所以 `/memory confirm` 写下的偏好在**下一轮**就生效，不用等下一个会话。

---

### 3.5 真 bug：MCP 的 `url` 和 `headers` 配了但不生效 ✅ 已修

**原来**：`src/coderagent/config/schema.py:117-124` 的 `MCPServerConfig` 里有
`url`（http 传输的地址）和 `headers` 两个字段，文档里也写着它们能用。但是
`src/coderagent/tools/mcp.py` 里**从头到尾没有出现过 `url` 或 `headers`**——
`MCPManager.start()` 在 `mcp.py:182` 只认 `server.command`：

```python
if not server.enabled or not server.command:
    continue
```

**影响**：配了 `url:` 的 MCP server **被静默跳过**——不启动、不报错、不出现在
`/mcp` 的状态里。用户看 `/mcp` 只看到「没有连上的 server」，根本猜不到是配置字段没用。

**怎么修的**：http 传输**实现了**（`streamable_http`），`headers` 跟着每个请求发出去；
`command` 和 `url` 同时给会报错；两样都没有的 server 不再沉默，`/mcp` 里写
`no command and no url`。另外：**本机上的 server 不走系统代理**（代理是给别的主机用的），
不然 macOS 上开着代理的机器连 `127.0.0.1` 的 server 会被代理挡回来。

---

## 4. P1：影响日常效率

| # | 差距 | 现状（指到文件） | Codex 有 | 工作量 |
|---|---|---|---|---|
| 4.1 | **没有图片/音频输入** | 消息只有文本：`core/context.py` 的 `build_messages()` 拼的是 `{"role","content"}` 字符串，没有多模态分支 | `/image` 附件（0.167/0.168 起支持图像与音频） | 中 |
| 4.2 | **没有输入历史** ✅ | TUI 的 `Input` 部件没有历史栈（`src/coderagent/ui/tui.py` 里没有相关实现），上下键只能移动光标 | 上下键翻历史 | 小 |
| 4.3 | **回答不渲染 Markdown** | TUI 直接把原文塞进 `Static`（`tui.py:197`），代码块、表格、标题都是平的 | 富渲染 | 中 |
| 4.4 | **中断的粒度是「轮」** | `loop.cancel` 只在**每轮模型调用之前**检查（`src/coderagent/core/loop.py:179-181`），`tools/executor.py` 里没有取消检查——**一条跑着的 `bash` 停不下来**，只能等它自己结束 | 能中断正在跑的工具 | 中 |
| 4.5 | **没有 @ 提及文件** ✅ | 输入框里 `@foo.py` 不会被展开成路径 | `@` 补全文件 | 小 |
| 4.6 | **TUI 没有文件树** | 文件树只在网页版左栏（`src/coderagent/web/`）；终端里只能靠 `ls` 工具 | 侧栏文件树 | 中 |
| 4.7 | **TUI 没有会话切换器** ✅ | 终端里切会话要 `/resume`（`builtin.py:437`），是一个列表文本 | 会话切换面板 | 小 |
| 4.8 | **没有终端通知** ✅ | 跑完一轮没有任何通知；长任务跑完时人不在屏幕前就不知道 | OSC 777 通知（可配） | 小 |
| 4.9 | **没有 `apply_patch` 工具** | 改文件用 `write` / `edit` / `multi_edit`（`src/coderagent/tools/builtin/fs.py`），是整串替换 | `apply_patch`（带上下文的块补丁） | 中 |

关于 4.9 要说句公道话：`edit` 的 `old_string` 匹配逻辑（`fs.py:36-58`）已经处理了
CRLF 变体和「不唯一」的报错，可读性不错。**`apply_patch` 的真正价值是模型侧更省 token**
（块补丁比整段内容短），不是功能更多。所以这条排 P1 而不是 P0。

### 4.2 / 4.5 / 4.7 / 4.8 TUI 小件 ✅ 已修

四个小改动合在一起做，都是「有了就顺手」：

- **输入历史（4.2）**：`CoderApp` 记住发出去的消息，上下键在上面走，
  走过最新的一条就把正在写的那句还给你（`ui/tui.py` 的 `_show_history`）。
  翻历史的键和审批面板的方向键不打架：面板在的时候方向键归面板。
- **`@` 补全（4.5）**：`ui/widgets/path_suggester.py` 里的 `PathSuggester` 是
  textual 的 `Suggester`：输入框里敲 `@src/app`，补全出这个文件的路径，
  `→` 收下。补的是**工作目录里**的文件，隐藏目录和 `node_modules` 这些不看。
- **会话面板（4.7）**：`ctrl+o` 打开 `ui/widgets/session_picker.py`：
  这个目录的会话一个一个列出来，`enter` 接着选中的那个继续
  （`loop.switch_to` 换会话，屏幕上的对话也重画成那个会话的），
  `escape` 关掉。`/resume` 还在，它给的是文字列表。
- **终端通知（4.8）**：一轮结束时给终端发 **OSC 777** 的通知序列
  （`ui/notify.py` 的 `escape_sequence`），内容是 agent 的回答。
  终端认不认这套序列是终端的事；`ui.notifications: false` 可以关掉。

**为什么是 `ctrl+o`**：textual 自己把 `ctrl+p` 拿去做命令面板了，
`ctrl+s` 在有些终端里会截住（XON），`ctrl+q` 已经用来退出了。

---

## 5. P2：清理与锦上添花

### 5.1 死配置 ✅ 已修

| 配置项 | 位置 | 原来 | 现在 |
|---|---|---|---|
| `ui.theme` | `config/schema.py`、`config/defaults.yaml` | **全仓没有任何地方读它** | **删了** |
| `ui.show_reasoning` | `config/schema.py`、`config/defaults.yaml` | **全仓没有任何地方读它** | **删了** |
| `model.max_retries` | `config/schema.py` | 只有网页版服务器用（`web/server.py` 把它写进环境变量），**终端里配了不生效** | **每个界面都生效** |

**怎么做的**

- 两个没人读的键直接删掉。不存在的键本来就被静默忽略（文档里写着），
  所以旧配置文件不会报错。
- `model.max_retries` 改成**从配置走到 backend**：
  `LiteLLMBackend` 多一个 `max_retries`，重试的时候交给它
  （`minisweagent/models/utils/retry.py` 的 `retry()` 多一个 `attempts` 参数）。
  主模型、`model.routing` 的子模型、`/model` 换模型、自定义命令、网页版的
  连接测试——**每一处**建 backend 的地方都带上这个数。
- 网页版的两处「环境变量 hack」删了：服务器不再设
  `MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT`，连接测试也不再临时改它，
  改成 backend 上的 `max_retries=1`。
- **优先级**：`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT`（环境变量）›
  `model.max_retries`（配置）› 10（默认）。环境变量留着当测试的开关。
- **顺带**：终端的重试次数从 **10** 变成 **3**（配置的默认值），
  和浏览器一样了；这也算 §5.2 那条 complaint 的一半。

### 5.2 认证失败要重试十分钟

`src/coderagent/models/backends.py:31-39` 的 `abort_exceptions` 里**没有**
`litellm.exceptions.InternalServerError`。中转站在**完全没有 key** 的时候返的是 500，
于是走满 10 次重试（约两分钟）才放弃；而 **key 写错**的时候返 `AuthenticationError`，
在列表里，立即失败。**同一个错，两种体验。**

建议把 `InternalServerError` 加进 `abort_exceptions`，或者只在「明确是配额/限流」时重试。

**顺带变了**：重试次数现在跟着 `model.max_retries` 走（默认 **3**，见 §5.1），
所以「完全没有 key」的那种失败现在等的是三次而不是十次（约半分钟，不是两分钟）。
根子上的问题还在：500 和「key 不对」走的路不一样。

### 5.3 `AGENTS.md` 会话中途改了不生效

`src/coderagent/core/context.py:109-110` 在 `ContextEngine` 构造时读一次指令文件，
之后只追加**子目录**的指令（`context.py:392-395`）。项目根目录的 `AGENTS.md`
在会话开始后被修改，模型这一轮还看的是旧内容。

Codex 的做法是每次会话开始、每次 compact 之后重读。**工作量：小**（把「读指令」
挪到和记忆同一层的「每轮重算」里）。

### 5.4 hook 事件只有 6 个

现在有：`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`Stop`、`SessionStart`、`SessionEnd`
（`src/coderagent/tools/executor.py:104,169`、`src/coderagent/core/loop.py:145,364,372,376`）。

Codex 还提供压缩前后、通知、子 agent 停止等事件。`PreCompact` 对本项目特别有用——
压缩是 coderagent 的核心机制之一（见[上下文专题](coderagent-context.md)），
压缩前后的钩子是天然的「记录摘要质量」的地方。

### 5.5 自定义命令只有项目级，`allowed-tools` 太粗

`src/coderagent/ui/custom_commands.py:54` 只从 `<cwd>/.coderagent/commands` 读，
没有用户级目录——**用户没法给自己装一套全局命令**。
`allowed-tools` 在 `custom_commands.py:51` 被 `_split_tools` 按 `spec.split("(")[0]`
截断，所以 `bash(git diff:*)` 里的**参数模式整个丢掉**，只剩工具名。

### 5.6 OTel 只是本地 JSON

`src/coderagent/core/telemetry.py:119` 的 `otel()` 返回一份 OTLP/JSON 的 **dict**，
没有 exporter，不往任何地方发。要接真正的 OTel 后端，还差一个 exporter。

### 5.7 其它零碎

- `src/coderagent/core/instructions.py:12` 的 `PROJECT_FILES` 常量定义了但**没人用**（死代码）。
- 网页版的改动列表来自会话的检查点（`api.py:175` 的 `/changes`），
  没有检查点的改动不会出现在列表里（这条已经写进 `docs/usage/coderagent_web.md` 的「已知差距」）。

---

## 6. coderagent 比 Codex 强的地方（不要照抄 Codex 时弄丢）

| 能力 | Codex | coderagent |
|---|---|---|
| **信任边界** | 项目配置可以带 MCP server、hook | **项目只能拿走能力，不能给能力**（`src/coderagent/core/trust.py`）：模式只留 plan/readonly、规则只留 deny、路径取并集、工具取交集 |
| **路径边界** | 由沙箱决定 | `within_bounds()` 在**所有**模式下都生效，**用户的 `allow` 规则也放宽不了** |
| **事实来源** | 会话状态 | **事件日志是唯一事实来源**，压缩只把原文移出窗口，不删事实 |
| **离线评测** | 有 `codex exec`，但没有可对比的指纹 | `coder eval` + `coder eval-compare` + 指纹，**能测出「harness 坏了」**（模型会绕开坏掉的 `edit`，只数工具调用是测不出来的） |
| **网页版** | 有 IDE 扩展，没有完整的网页终端 | 完整的网页版：SSE 流式、三栏、会话列表、设置页分层预览、审批卡片 |
| **审批粒度** | on-request / on-failure / never | **`Always allow` 会往 `~/.coderagent/rules.yaml` 写规则**，规则本身是文件、可读可改 |

**做 OS 级沙箱时最该小心的一件事**：Codex 的 `approval_policy=never` 允许完全放开；
coderagent 的 `bypass` 模式语义类似，但它建立在「所有副作用过同一道闸」之上。
加了沙箱之后，**闸和沙箱是两层，不是二选一**——`bypass` 应该绕过审批，**不应该**绕过路径边界。

---

## 7. 不建议照抄 Codex 的地方

| Codex 的做法 | 为什么别抄 |
|---|---|
| `approval_policy=never` 一个人类完全不在场的档 | coderagent 的 `bypass` 已经是这个东西，但它是**显式选的**；不要顺手给它一个默认值 |
| 沙箱策略和审批策略绑在一起理解 | Codex 已经拆成两个正交的轴了，这一条照抄是对的（见 3.1） |
| 把一切都做成 slash 命令 | coderagent 的命令有 20 多条了，再加就要有 `/help` 的分类。Codex 的命令更多是因为它的用户群更杂 |
| 把 trace 交给云端 | coderagent 的事件日志在本地，评测能离线跑——这是它最值钱的地方，别动 |

---

## 8. 建议的推进顺序

| 顺序 | 做什么 | 为什么排这个位置 |
|---|---|---|
| 1 | ~~**修 3.4 + 3.5 两个 bug**~~ ✅ | 都是几行的事，但一个白烧 token、一个静默吞配置 |
| 2 | ~~**加网络开关（3.1 的第一步）**~~ ✅ | 一天内能做完，堵住最大的口子 |
| 3 | ~~**`/review`（3.2）**~~ ✅ | 现有零件都齐了，性价比最高的功能缺口 |
| 4 | ~~**`reasoning_effort`（3.3）**~~ ✅ | 便宜，且和 `model.routing` 是一套东西 |
| 5 | ~~**TUI 小件（4.2 / 4.5 / 4.7 / 4.8）**~~ ✅ | 四个小改动合一个提交，都是「有了就顺手」 |
| 6 | ~~**死配置清理（5.1）**~~ ✅ | 顺手做，别单开 |
| 7 | ~~**OS 级沙箱（3.1 的第二步）**~~ ✅ | 最大的一件，做完前面再说 |
| 8 | 图片输入（4.1）、中断粒度（4.4）、Markdown（4.3） | 需要设计，不适合顺手做 |

---

## 附录：这份清单是怎么来的

1. 读 Codex 的文档：sandbox 与 approval 的两个轴、OS 级隔离、命令集、多模态输入、
   终端通知。
2. 读 coderagent 的源码，逐条对：`core/sandbox.py`、`tools/permissions.py`、
   `tools/bash_policy.py`、`ui/commands/builtin.py`、`ui/tui.py`、`extensions/hooks.py`、
   `core/context.py`、`core/instructions.py`、`core/memory.py`、`tools/mcp.py`、
   `models/backends.py`、`config/schema.py`、`core/telemetry.py`。
3. 每一条结论都指到了文件；**行号会漂**，本文里的 `file:NN` 只在写下的那天成立——
   核对时请按函数名找。

> 本文中标注「真 bug」的两条（3.4、3.5）已经在写这份文档时用源码确认过，
> 也都修了：3.4 让一个文件只出一段（`core/instructions.py` 的 `once_per_file()`），
> 3.5 把 http 传输和 `headers` 实现了（`tools/mcp.py`）。两条都有回归测试。
