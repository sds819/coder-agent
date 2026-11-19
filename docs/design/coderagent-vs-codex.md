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

**进度**：§8 的第 1～10 步都做完了（两个 bug、网络开关、`/review`、`reasoning_effort`、
TUI 小件、死配置清理、OS 级沙箱、图片输入 + 中断粒度 + Markdown、
`apply_patch` + TUI 文件树 + P2 清理一批、OTel exporter + 第二轮对照的差距）。
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
- **项目不能决定命令在哪里跑**：沙箱的 `type` 和环境的那些选项（`image` 等等）
  都从项目层丢掉——`tightened()` 只留下 `mode`（`core/trust.py`）。项目的环境会
  把用户的工作目录一起带走，那个选择归用户；
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
- 审查轮在**当前会话**里跑，结果留在对话里，用户可以接着说「把第二条改掉」；
- **diff 只在这一轮里**：轮结束就换成一句提示（「改动不在上下文里了，自己再读一遍」），
  否则一次大审查就把整个会话的窗口吃掉了。

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

- `src/coderagent/core/instructions.py:66` — `load_instructions()` 读
  `home / USER_FILE`，`USER_FILE = "CLAUDE.md"`（`instructions.py:12`），
  于是读的是 `~/.coderagent/CLAUDE.md`；
- `src/coderagent/core/memory.py:36` — `load_user_memory()` 读
  `home / Path(config.user_path).name`，而 `user_path` 的默认值就是
  `~/.coderagent/CLAUDE.md`（`src/coderagent/config/schema.py:108`）；
- 这两块在 `src/coderagent/core/context.py:270-293` 被**同时**拼进指令段。

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
| 4.1 | **没有图片/音频输入** ✅ | 消息只有文本：`core/context.py` 的 `build_messages()` 拼的是 `{"role","content"}` 字符串，没有多模态分支 | `/image` 附件（0.167/0.168 起支持图像与音频） | 中 |
| 4.2 | **没有输入历史** ✅ | TUI 的 `Input` 部件没有历史栈（`src/coderagent/ui/tui.py` 里没有相关实现），上下键只能移动光标 | 上下键翻历史 | 小 |
| 4.3 | **回答不渲染 Markdown** ✅ | TUI 直接把原文塞进 `Static`（`tui.py:197`），代码块、表格、标题都是平的 | 富渲染 | 中 |
| 4.4 | **中断的粒度是「轮」** ✅ | `loop.cancel` 只在**每轮模型调用之前**检查（`src/coderagent/core/loop.py:281`），`tools/executor.py` 里没有取消检查——**一条跑着的 `bash` 停不下来**，只能等它自己结束 | 能中断正在跑的工具 | 中 |
| 4.5 | **没有 @ 提及文件** ✅ | 输入框里 `@foo.py` 不会被展开成路径 | `@` 补全文件 | 小 |
| 4.6 | **TUI 没有文件树** ✅ | 文件树只在网页版左栏（`src/coderagent/web/`）；终端里只能靠 `ls` 工具 | 侧栏文件树 | 中 |
| 4.7 | **TUI 没有会话切换器** ✅ | 终端里切会话要 `/resume`（`builtin.py:437`），是一个列表文本 | 会话切换面板 | 小 |
| 4.8 | **没有终端通知** ✅ | 跑完一轮没有任何通知；长任务跑完时人不在屏幕前就不知道 | OSC 777 通知（可配） | 小 |
| 4.9 | **没有 `apply_patch` 工具** ✅ | 改文件用 `write` / `edit` / `multi_edit`（`src/coderagent/tools/builtin/fs.py`），是整串替换 | `apply_patch`（带上下文的块补丁） | 中 |

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

### 4.1 / 4.3 / 4.4 图片、Markdown 与中断粒度 ✅ 已修

这三件事凑在一起做，因为它们都在**消息这一层**：消息长什么样、怎么显示、
什么时候能停下来。

- **图片输入（4.1）**：消息的内容不再只是字符串，可以是**部件的列表**
  （`core/content.py`）——`{"type":"text"}` 和 `{"type":"image_url"}` 两种，
  跟模型那边要的一样。`AgentLoop.run_turn()` 收字符串，也收这样的列表。
  终端里用 `/image <路径> [要它做什么]` 发图：文件读成 base64 的 data url，
  跟这句话一起进模型。**图片也进事件日志**（日志是唯一事实来源，重放要一样），
  所以日志会大一号——这是有意的取舍。
  - **限制**：只支持图片（`png`/`jpg`/`gif`/`webp`），**音频没做**；
    单张图不超过 5 MB，超了直接拒绝，不硬发。
  - **算 token**：`core/tokens.py` 认图片了——按像素估（宽 × 高 ÷ 750），
    估出来的数字跟模型那边的真实消耗同一量级。不然一张图在预算里几乎不算钱，
    等模型说「上下文太长了」才发现。
  - **别的地方也得认这个形状**：摘要（`core/summarize.py`）不能把 base64
    塞进提示词里、渲染（`ui/render.py`）不能把列表直接打印出来、
    网页版（`web/events.py`）不能把列表塞进气泡。这些都走 `text_of()` /
    `describe_message()`。
  - **hook 还能改写带图的消息**：`UserPromptSubmit` 拿到的还是文字，
    改写之后图片原样留着。
- **Markdown（4.3）**：回答说完之后用 textual 的 `Markdown` 部件渲染
  （`ui/widgets/markdown_message.py`），代码块、表格、列表跟项目 README 里一样。
  **文字流出来的时候还是纯文本**——半个代码块没什么可渲染的；说完了才换过去。
  `ui.markdown: false` 可以让它一直是纯文本。
- **中断粒度（4.4）**：中断信号现在能传到**正在跑的工具**。
  - 链路：`loop.cancel` → `run.py` 把 `ctx.cancel` 接上 → `ToolExecutor._run()`
    发现这一轮已经被打断，**工具根本不启动** → `BashTool` 把命令交给
    `CodingEnvironment.execute_cancellable()`，它每 50 毫秒问一次「这一轮还在吗」，
    不在了就**杀掉整个进程组**（先 TERM 后 KILL），它自己起的那些进程一起没。
  - **用户自己的命令不受影响**：verify 的检查命令不走这条路，和沙箱一个道理——
    那是**你的**命令，不是 agent 的。
  - **远端沙箱里停不掉**：命令跑在容器里的时候，只能等它跑完，这一轮再停。

### 4.6 / 4.9 文件树与 `apply_patch` ✅ 已修

这两件凑在一起做，因为它们都在**「改文件」这件事的边上**：一个让模型改得更省，
一个让人看得见改了什么。

- **`apply_patch`（4.9）**：新工具 `src/coderagent/tools/builtin/patch.py`，
  补丁格式跟 Codex 一样——`*** Begin Patch` / `*** Update File:` / `@@` 块 /
  `*** Add File:` / `*** Delete File:` / `*** End Patch`。
  - **块是靠内容定位的**，不是靠行号：`@@` 后面那段只是「大概在哪儿」的提示，
    真正要对上的是那一段上下文（先精确匹配，再退一步容忍行尾空格）。
    定位时会往后找，优先落在上一块后面，所以同一文件里连着几块也不会互相踩。
  - **要么全成要么全不成**：先把所有文件都算出来，任何一块对不上就一个文件
    都不动。`multi_edit` 是这个性质，这里也是。
  - **它没有绕过任何一道闸**：它是写工具（要审批、只读沙箱里被拒）、
    是串行工具（不能并发跑）、每个碰到的路径都要过 `within_bounds()`——
    它的参数里没有 `path`，策略自己看不见，所以工具自己查。
  - **检查点**：一个补丁能改好几个文件，所以工具多了一个 `touched_paths(params)`，
    执行器按路径逐个 `before_write`，每个改动的文件都有检查点。
  - 审批卡片上显示的是补丁的 diff（`ui/widgets/diff_view.py` 的 `prospective_diff`）。
- **TUI 文件树（4.6）**：`src/coderagent/ui/widgets/file_tree.py`，
  textual 的 `Tree`，`ctrl+t` 在左边打开，三层深。
  - **改过的文件有标记**：`git status --porcelain` 的结果映射成
    `+`（新增）、`●`（改过）、`-`（删了）、`?`（新文件）。
    不是 git 仓库时就没有标记，树照样能看。
  - **点一下就把路径填进输入框**——接着 `@` 那套补全用。
  - 每轮跑完刷新一次，文件树跟工作目录同步。

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

### 5.2 认证失败要重试十分钟 ✅ 已修

`src/coderagent/models/backends.py:31-39` 的 `abort_exceptions` 里**没有**
`litellm.exceptions.InternalServerError`。中转站在**完全没有 key** 的时候返的是 500，
于是走满 10 次重试（约两分钟）才放弃；而 **key 写错**的时候返 `AuthenticationError`，
在列表里，立即失败。**同一个错，两种体验。**

建议把 `InternalServerError` 加进 `abort_exceptions`，或者只在「明确是配额/限流」时重试。

**顺带变了**：重试次数现在跟着 `model.max_retries` 走（默认 **3**，见 §5.1），
所以「完全没有 key」的那种失败现在等的是三次而不是十次（约半分钟，不是两分钟）。
根子上的问题还在：500 和「key 不对」走的路不一样。

**怎么做的**：500 不一刀切地不重试——**有的 500 值得等**（服务端真的抖了）。
所以改成**看错误文本**：`models/backends.py` 的 `is_auth_error()` 认
`api key` / `invalid token` / `unauthorized` / `authentication` 这些说法，
命中就把 500 换成 `AuthenticationError`——它在 `abort_exceptions` 里，重试立刻停。
没命中就照旧重试。**key 不会因为等一会儿变好，等待只是让用户多等。**

### 5.3 `AGENTS.md` 会话中途改了不生效 ✅ 已修

`src/coderagent/core/context.py:118-120` 在 `ContextEngine` 构造时读一次指令文件，
之后只追加**子目录**的指令（`context.py:532-544`）。项目根目录的 `AGENTS.md`
在会话开始后被修改，模型这一轮还看的是旧内容。

Codex 的做法是每次会话开始、每次 compact 之后重读。**工作量：小**（把「读指令」
挪到和记忆同一层的「每轮重算」里）。

**怎么做的**：`ContextEngine` 多了一个 `reload_instructions` 标志——
**没显式给指令**的时候（`instructions=None`）每轮重读 `AGENTS.md` / `CLAUDE.md`，
**显式给了**的就以给的为准，不再重读（那是调用方的意思，不是项目的）。
重读发生在 `_instruction_text()` 里，也就是**每轮组消息的时候**，
所以项目中途改了规则，下一轮模型就看见了。

### 5.4 hook 事件只有 6 个 ✅ 已修

现在有：`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`Stop`、`SessionStart`、`SessionEnd`
（`src/coderagent/tools/executor.py:104,169`、`src/coderagent/core/loop.py:241,495,505,509`）。

Codex 还提供压缩前后、通知、子 agent 停止等事件。`PreCompact` 对本项目特别有用——
压缩是 coderagent 的核心机制之一（见[上下文专题](coderagent-context.md)），
压缩前后的钩子是天然的「记录摘要质量」的地方。

**怎么做的**：加了三个事件，都是**通知**（改不了什么）：

| 事件 | 什么时候 | 读到什么 |
|---|---|---|
| `PreCompact` | 压缩之前 | `messages`（马上要走的那几条）、`turn` |
| `PostCompact` | 压缩之后 | `summary`、`messages`（压掉几条）、`tokens`、`summary_tokens` |
| `SubagentStop` | 子 agent 结束 | `agent`、`status`、`summary`、`files_touched` |

`PreCompact` / `PostCompact` 挂在 `ContextEngine.compact()` 上（它拿得到
`self.hooks`），`SubagentStop` 挂在 `SubAgentRunner.run()` 的收尾上。
后两个 token 数就是评测报告里那个 `summary_ratio` 的原料——
**摘要质量从此可以被 hook 量出来**。

### 5.5 自定义命令只有项目级，`allowed-tools` 太粗 ✅ 已修

`src/coderagent/ui/custom_commands.py:54` 只从 `<cwd>/.coderagent/commands` 读，
没有用户级目录——**用户没法给自己装一套全局命令**。
`allowed-tools` 在 `custom_commands.py:51` 被 `_split_tools` 按 `spec.split("(")[0]`
截断，所以 `bash(git diff:*)` 里的**参数模式整个丢掉**，只剩工具名。

**怎么做的**：

- **用户级目录**：`~/.coderagent/commands/*.md`（和子 agent、技能一个位置）。
  **同名时项目里的那个算数**——它是属于眼前这份活的。
- **`allowed-tools` 的模式成了真的限制**：`CustomCommand.tool_rules()` 把
  `bash(git diff:*)` 变成 `{"bash": "git diff"}`，交给权限策略的
  `restriction`。这个限制**在每种模式下都在**（连 `bypass` 也一样），
  **用户的规则也放宽不了它**——`evaluate()` 第一步就查它。
  没写出来的工具就是没有；`bash` 的每一段命令都要对得上那个模式。

### 5.6 OTel 只是本地 JSON ✅ 已修

**原来**：`src/coderagent/core/telemetry.py` 的 `otel()` 返回一份 OTLP/JSON 的 **dict**，
没有 exporter，不往任何地方发。

**怎么做的**：新模块 `src/coderagent/core/otel.py`，两件事分开做——
**把事件算成合法的 OTLP**，和**把它发出去**。

**一、span 算对了**

- **span 是平的**：原来把子 span 塞在父 span 的 `"spans"` 字段里，
  那**不是 OTLP 的形状**（OTLP 没有「span 里面再套 span」这回事），
  后端读不懂。现在一轮一个 span、一次模型调用一个 span、一次工具调用一个 span，
  子 span 用 `parentSpanId` 挂在父 span 上，全部平铺在 `scopeSpans[].spans` 里。
- **span 有长度**：原来每个 span 的起止时间都是同一个时间戳（长度为零），
  现在一轮从提问到结束、一次工具调用从调用到结果。
- **钱在 span 上**：`turn.cost`、`cost`、`tokens.in`、`tokens.out`；
  失败的工具是 `status.code = 2`；一轮的 `stop_reason` 也是属性。
- **一轮之前的事情不算一轮**：会话刚建好时那些状态事件不产生 span。

**二、真的发出去**

- `OtlpExporter` 走 **OTLP/HTTP**（JSON），发到 `telemetry.otel_endpoint`；
  `telemetry.otel_headers` 是给那些要 key 的后端用的。
- **每轮结束发一次**：发的是这一轮的新 span，**每个 span 只发一次**；
  `switch_to` 换了会话就重新开始。
- **后端不在只是警告**：会话照常往下走，追踪下一轮再发（失败的那轮也会补发）。
- **事件日志仍然是唯一的事实**：追踪是从日志算出来的，日志照写不误。
- **手动发**：`coder export --format otel --push` 把一个会话推到配置的地址上。
- **信任边界**：追踪里是 agent 读过的东西，**项目不能把它送到自己的地址**
  （`core/trust.py` 的 `tightened()` 只留下「关掉」那一种，项目带的 header 也丢掉）；
  **用户也不能把项目关掉的追踪重新打开**（`config/loader.py`）。
  「追踪发到哪里」是用户的决定，不是克隆下来的仓库的决定。

### 5.7 其它零碎 ✅ 已修（一条改代码，一条写文档）

- `src/coderagent/core/instructions.py:12` 的 `PROJECT_FILES` 常量定义了但**没人用**（死代码）。
  —— **删了**。
- 网页版的改动列表来自会话的检查点（`api.py:175` 的 `/changes`），
  没有检查点的改动不会出现在列表里（这条已经写进 `docs/usage/coderagent_web.md` 的「已知差距」）。

---

## 6. coderagent 比 Codex 强的地方（不要照抄 Codex 时弄丢）

| 能力 | Codex | coderagent |
|---|---|---|
| **信任边界** | 项目配置可以带 MCP server、hook | **项目只能拿走能力，不能给能力**（`src/coderagent/core/trust.py`）：模式只留 plan/readonly、规则只留 deny（写坏的规则也算 deny）、路径取并集、工具取交集、**`model` 整段丢掉**（项目的端点会把对话和用户的 key 一起带走）、**`context.summarize_model` 丢掉**、**项目命令里的 `model` 清掉**、**`ui.file_opener` / `ui.notify_command` / `sandbox.type` 丢掉**（跑在用户机器上的程序归用户挑）、**`shell_environment.set` 丢掉**（项目自己的 `LD_PRELOAD` 会跑在用户机器上）、**`context.context_window` 丢掉**（窗口是模型的）、**会话的上限只能往下压**（`config/loader.py` 的 `_tighten_limits`） |
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
| 8 | ~~**图片输入（4.1）、中断粒度（4.4）、Markdown（4.3）**~~ ✅ | 三件事都在消息这一层，一起做 |
| 9 | ~~**`apply_patch`（4.9）、TUI 文件树（4.6）、P2 清理一批（5.2～5.5、5.7）**~~ ✅ | 一块改文件的东西，一块看文件的东西，剩下的都是收尾 |
| 10 | ~~**OTel exporter（5.6）+ 第二轮对照的差距（§9）**~~ ✅ | 先把追踪发出去，再把 Codex 的清单整个重读一遍，找剩下的差距 |
| 11 | ~~**第三轮的差距（§9.6）**~~ ✅ | 两个安全向的先做（环境变量、工具输出上限），再把小的补齐 |
| 12 | ~~**第三轮剩下的差距（§9.6）**~~ ✅ | 会话的生命周期和历史的保留策略，加上两个小的 |
| 13 | ~~**§9.6 最后一条**~~ ✅ | 一份总结（`/recap`）和一段岔开的对话（`/side`） |

第 12 步做掉了 §9.6 里剩下的**两个中的**（`file_opener`、
`supports_parallel_tool_calls`）和**两个大的**（会话的生命周期、历史的保留策略）。
第 13 步做掉了 §9.6 里**最后一条**：`/recap` 和 `/side`——它们要的是新的会话形态，
所以顺带把「工具和检查点属于哪个会话」这个真 bug 一起修了。

---

## 9. 第二轮对照：又找到的差距

第一轮读的是 Codex 文档里最显眼的几页（沙箱、审批、命令集、多模态）。
第二轮把 Codex 的**全部**配置键、命令、开关、子命令和周边产品摊开重读了一遍，
再逐条对 coderagent 的源码。这一轮找到的差距不多，但有四条是真的：

| # | 差距 | Codex 有 | coderagent 当时的样子 | 工作量 |
|---|---|---|---|---|
| 9.1 | **没有命名 profile** | `[profiles.<name>]` + `codex -p <name>` | 只有 `-c key=value` 的一次性覆盖，每次都要把一串键抄一遍 | 小 |
| 9.2 | **输出不能约束成结构化的** | `codex exec --output-schema schema.json` | `--output-format json` 的形状是写死的，脚本只能自己再解一遍 | 中 |
| 9.3 | **MCP 服务器的工具不能挑着露出** | 每个服务器有 `enabled_tools` / `disabled_tools` | 服务器给什么就全给什么，想藏一个工具就得关掉整个服务器 | 小 |
| 9.4 | **`@文件` 只剩下一个路径** | `/mention <file>`（终端）和 `@` 引用（IDE）把**内容**带进消息 | TUI 会补全路径，但模型只看见 `@src/app.py` 这几个字，内容得它自己再读一遍 | 中 |

### 9.1 命名 profile ✅ 已修

**怎么做的**：

- 配置里多了一张表：`profiles: {名字: {一截配置}}`，选中哪个由 `profile:` 说了算，
  命令行上也可以 `--profile`（短写 `-p`）。
- **profile 压在用户配置上面**，和 `-c` 一样是「临时的覆盖」；
  **项目的收紧仍然压在最上面**——profile 不能把项目关掉的沙箱和网络再打开。
- **项目不许定义 profile，也不许选 profile**：`core/trust.py` 把项目层里的
  `profile` 和 `profiles` 丢掉。理由和 5.6 一样——**选哪套权限是用户的决定**，
  克隆下来的仓库不能替用户挑一套宽松的。

### 9.2 结构化输出 ✅ 已修

**怎么做的**：

- `--output-schema <文件>`：最后一条回答**必须是符合这个 schema 的 JSON**。
  合上的答案放在这一轮 JSON 的 `output` 字段里。
- **schema 也给模型看**：系统提示词后面附上一段 `<output_schema>`，说清「只答 JSON，不要散文」。
- **不合格就再来一次**：回答不是合法 JSON、或者对不上 schema，
  把**错在哪儿**写回去让模型改，最多两次（第二次还不对就以 `schema_invalid` 停下）。
- **不引依赖**：仓库里没有 `jsonschema`，所以校验器是自己写的
  （`core/schema.py`，认 `type` / `properties` / `required` / `additionalProperties` /
  `items` / `enum` / `nullable` 这几样）。这是刻意的：为了一个功能装一个包不划算。
- **Codex 是靠模型服务端约束的**，coderagent 走的是 litellm，好几个 provider 不认那个参数，
  所以这边是「提示 + 校验 + 重试」。**慢一点，但每个 provider 都一样。**

### 9.3 MCP 服务器的工具过滤 ✅ 已修

**怎么做的**：`enabled_tools`（只露这些）和 `disabled_tools`（这些不露），
两个都能按名字筛一个服务器的工具，`*` 表示全部。
**过滤只减不增**：`enabled_tools` 空着就是全给，`disabled_tools` 里的名字一定不露。

### 9.4 `@文件` 的内容进消息 ✅ 已修

**怎么做的**：

- 提问里的 `@路径`（终端界面和命令行里都直接写）和 `/mention <文件>` 都会把
  **文件的内容**带进消息，模型不用自己再花一次工具调用去读。
- **不是文件的名字就当没写**：`@` 还有别的用处（邮箱、装饰器），
  所以只有真的存在的文件才会被打开（`core/mentions.py`）。
- **守路径边界**：工作目录外面的文件、被 `deny_paths` 挡住的文件**不带**，
  消息里写明「这个文件不让看」，而不是把内容偷偷塞进去。
- **只带文本**：不是文本的文件只被点名；图片走 `/image`，不在这里重复一套。
  超过 20000 字符的文件会截断，并且说明截断了。

### 9.5 这一轮看懂了但不抄的

| Codex 的做法 | 为什么不抄 |
|---|---|
| `--search` / `web_search` 的四档（cached / indexed / live / disabled） | web 搜索是**模型服务端**的工具。coderagent 走 litellm，十来家 provider 里只有一部分有，**做不出「一个开关全都行」**。要做就得按 provider 分叉，那是另一个项目 |
| `codex cloud` / GitHub Action / 桌面应用 | 那是**云**。coderagent 的评测要能离线跑，事件日志在本地，这是它最值钱的地方（见 §6） |
| MCP 的 resources 和 prompts | Codex 自己也只是「部分支持」——**不值得为一个半吊子的对标去实现** |
| `tui.keymap`（自定义键位） | textual 自己有一套键位，配置化的收益不如上面那四条 |
| `personality`（`friendly` / `pragmatic`） | 那是一段塞给模型的话。coderagent 的 `agent.system_prompt` 就是它，一样的东西换个名字 |

### 9.6 第三轮：还有一批差距，先记下来

第 10 步做完之后，又拉了一份 Codex 的**全量清单**（全部配置键、slash 命令、子命令、
CLI 选项、周边产品），再逐条对 coderagent 的源码。这一轮**没有马上做**——
它们要么是锦上添花，要么该等第 10 步的提交落地之后再挑。这节只作记录。

> 第 11 步之后，这一节里**六个小的和两个中的都做掉了**（见 §9.7）；
> 第 12 步之后，**两个中的和两个大的也做掉了**（见 §9.8）；
> 第 13 步之后，**最后那条也做掉了**（见 §9.9）。
> 表里打 ✅ 的就是它们。

**已经有的、不用再抄的**（对过命令表和配置 schema）：`/diff`、`/init`、`/status`、
`/fork`、`/compact`、`/permissions`、`/skills`、`/mcp`、`/export`、`/hooks`、
`/agents`、`/todos`、`/cost`、`/context`、`/sandbox`、`/plan`、`/mode`、
`--profile`、`--output-schema`、OTel、`/review`、`reasoning_effort`、图片、Markdown、
`apply_patch`、沙箱三档。

**小的**（一个配置键 / 一个选项的事）：

| 差距 | Codex 有 | coderagent 现在的样子 | 备注 |
|---|---|---|---|
| `model_verbosity`（回答的啰嗦程度） ✅ | `low \| medium \| high` | `model.verbosity`，同一套三档 | 和 3.3 是同一套东西，翻译逻辑照抄那一段 |
| `review_model` ✅ | `/review` 可以用另一个模型 | `model.review_model`，`model.routing.review` 压过它 | 多一个模型槽位 |
| `project_doc_max_bytes` ✅ | AGENTS.md 塞进上下文有字节上限（默认 32768） | `context.project_doc_max_bytes`，默认一样 | 指令文件很大时会直接吃掉预算 |
| `--output-last-message` / `-o 文件` ✅ | 最后一条回答写进文件 | `--output-last-message` | 和 9.2 的 schema 常常一起用 |
| 外部通知程序 ✅ | `notify = ["notify-send", ...]` | `ui.notify_command`，还是 OSC 777 终端通知（4.8） | 是补充，不是替代 |
| MCP 每服务器超时 ✅ | `startup_timeout_sec` / `tool_timeout_sec` | `startup_timeout` / `tool_timeout`，不写就是全局的 30 秒 | 一个慢的服务器能拖死全部 |

**中的**：

| 差距 | Codex 有 | coderagent 现在的样子 | 备注 |
|---|---|---|---|
| `[shell_environment_policy]` ✅ | 控制哪些环境变量进子进程 | `shell_environment`：`inherit` / `exclude` / `include` / `set`，像秘密的名字**一定**被去掉 | **安全向，值得早点做** |
| `tool_output_token_limit` ✅ | 单个工具输出有 token 上限 | `tools.max_output_tokens`（默认 8000），**每一个**工具的结果都裁 | 一条十万字符的输出会当场顶爆预算 |
| `file_opener` ✅ | 文件引用点开 vscode / cursor / windsurf | `ui.file_opener` + `/open <路径>` | 纯终端的友好度 |
| `supports_parallel_tool_calls` ✅ | 按 MCP 服务器放开并行调用 | `mcp.servers[].supports_parallel_tool_calls`，默认 `true` | 慢 |

**大的**：

| 差距 | Codex 有 | coderagent 现在的样子 | 备注 |
|---|---|---|---|
| `/side`（临时岔开聊）、`/recap`（只总结不压缩） ✅ | 有 | 有了（见 §9.9） | 要新的会话形态，不是加一条命令 |
| `/rename` / `/archive` / `/delete` ✅ | 会话生命周期 | 只有新建 / 恢复 / 分叉 | 要动会话存储 |
| `history.persistence` / `max_bytes` ✅ | 历史保留策略 | 一直留着 | 长期跑会一直涨 |

**挑的时候**：先 `[shell_environment_policy]`（安全）和 `tool_output_token_limit`
（会炸预算），这两个的代价和收益都比别的高——第 11 步做的正是这两个。

### 9.7 第 11 步：做掉的那些 ✅ 已修

**怎么做的**：

- **`model.verbosity`**（`low` / `medium` / `high`）：**一句写进系统提示词的话**，
  不是厂商参数——所以哪家都听得懂。跟 `reasoning_effort` 是两回事：一个管想多久，
  一个管说多少。写错档位在**读配置时**就拒。
- **`model.review_model`**：`/review` 的那一轮带一个**用途**（`purpose="review"`），
  路由器按用途挑模型：`model.routing.review` 压过 `model.review_model`，
  两个都没有就还是会话自己的模型。用途写在事件日志的 `extra.purpose` 里。
- **`context.project_doc_max_bytes`**（默认 32768）：一个指令文件超了就被**截短**，
  而且**告诉模型**它没看全——不然模型会以为规则就那么长。
- **`--output-last-message`**：最后一条回答写进文件，就那一段文字。
- **`ui.notify_command`**：一个外部程序，拿到通知的**标题和正文**两个参数。
  跑不起来只是记一条警告。终端通知（OSC 777）还在，两者是补充关系。
  **项目不能挑通知程序**（`core/trust.py` 丢掉项目层的 `ui.notify_command`）——
  那个程序跑在用户的机器上，还拿着 agent 的回答。
- **MCP 每服务器超时**：`startup_timeout` 和 `tool_timeout`，不写就用全局的。
  一个慢的服务器拖不住别的了。
- **`shell_environment`**（**安全向**）：命令的环境里**像秘密的名字一定被去掉**
  （`*_API_KEY`、`*_KEY`、`*_TOKEN`、`*_SECRET`、`*_PASSWORD`、`*_PASSWD`、
  `*_CREDENTIALS`、`*_ACCESS_KEY`），除非用户用 `include` 一个一个地放回来。
  三个档位：`all`（除了秘密）、`core`（只有命令要的那些）、`none`（什么都没有）。
  **项目只能藏更多，不能把用户藏的放出来**（`core/trust.py` 丢掉项目的 `include`）。
- **`tools.max_output_tokens`**（默认 8000）：**每一个**工具的结果都裁，不只是 bash。
  裁的时候留头和尾，中间写明裁掉了什么；**完整的结果还留在事件日志里**。

### 9.8 第 12 步：会话的生命周期和历史的保留 ✅ 已修

**怎么做的**：

- **`ui.file_opener` + `/open <路径>`**：`vscode`、`cursor`、`windsurf` 是认得的名字，
  也可以是用户自己的命令（`my-editor {file} --wait`）。文件得在**工作目录里面**
  （走 `within_bounds`），不然 `/open` 会说它在边界外。
  **项目不能挑编辑器**——那个程序跑在用户的机器上，`core/trust.py` 把项目层的
  `ui.file_opener` 丢掉。
- **`supports_parallel_tool_calls`**（`mcp.servers[]` 上，默认 `true`）：
  一轮里模型可以同时调两个工具，MCP 的工具本来就在线程池里跑。
  所以这个开关**不是**「要不要并行」，而是「**这个服务器扛不扛得住两个调用**」：
  设成 `false`，**这个服务器的调用彼此排队**，别的服务器照旧并行。
- **`/rename` / `/archive` / `/delete`**：名字和「收起来了」这两个状态
  **写在事件日志里**（`STATE_CHANGE` 事件），和「事件是唯一的事实」这条一致——
  会话靠重放日志重建，重建出来的名字和归档状态也是对的。
  收起来的会话不在 `/resume` 的列表里，但还在盘上；`/archive` 再跑一次就拿出来。
  `/delete` 要 id，而且**不删你正待着的那个会话**。
- **`history.persistence` / `history.max_bytes`**：`save-none` 让会话只活在内存里
  （盘上什么都不写）；`save-none` 之外的默认值是 `save-all`。
  `max_bytes` 是**全部会话的历史**能占的字节数，超了就**从最老的开始删**，
  **正在跑的那个会话永远不在被删的里头**。

### 9.9 第 13 步：一份总结，和一段岔开的对话 ✅ 已修

**怎么做的**：

- **`/recap`（只总结，不动上下文）**：复用压缩的那套摘要机器（`core/context.py` 的
  `recap()`），但**不碰** `self.summaries`，**不碰**历史，也**不把摘要交给模型**——
  模型看到的还是整段对话。摘要只是**给你看的一份报告**，不是干活的一步。
- **摘要的钱记在会话上**：摘要用 `context.summarize_model` 跑（没配就是会话自己的模型），
  费用记到 `session.total_cost`，事件日志里是一条 `RECAP` 事件（带 `summary` / `text` / `cost`）。
  `collect()` 按用途 `recap` 归集，所以 `/cost` 里看得见这一笔。
- **`/side <问题>`（岔出去聊一条）**：当前会话**分叉**成一个新会话（`SessionStore.side()`），
  新会话知道自己的**父亲**（`metadata["parent"]`），**原来的会话一个字都没动**。
- **跑完就回来**：`AgentLoop.run_turn(..., session=...)` 会切到岔开的会话跑那一轮，
  然后切回来（`switch_to(..., start=False)`，所以 `SessionStart` 的 hook 不会响两次）。
  问题和回答记在**你当前会话**的日志里（一条 `SIDE_CONVERSATION` 事件），
  所以 agent 不会丢掉干活的线索——但也就这些：岔开的那些消息留在岔开的会话里，
  它用的工具也算在那个会话上。
- **岔开的会话有自己的 id**，跟别的会话一样能打开（`/resume <id>`）。
- **顺带修了一个真 bug**：工具和检查点**原来是在 build 的时候把会话钉死的**
  （`run.py`），所以 `/resume`、`/fork`、`/clear` 之后，工具的结果落进了**旧会话**的日志。
  现在工具的上下文、checkpoint 的回调、子 agent 的 `session_id` 都**跟着循环所在的会话走**。

**没做的**：这一轮把 §9.6 清空了。剩下的差距要等下一轮对照再看。

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

> **第二轮**（§9）把 Codex 的**全部**配置键、slash 命令、开关、子命令摊开重读了一遍
> （config.toml、命令集、CLI reference、sandboxing、approvals、MCP、多模态、
> 会话与历史、web search、skills/subagents/profiles/memory、UI 与周边），
> 再逐条对 coderagent 的源码。第一轮读的是最显眼的几页，第二轮读的是全部。

> **第三轮**（§9.6）第 10 步落地之后又拉了一份全量清单，对完源码，
> 剩下的差距**只记录、没做**——这一节就是那份记录。
> 第 11 步做掉了其中**八个**（六个小的 + 两个中的），见 §9.7；
> 第 12 步做掉了**四个**（两个中的 + 两个大的），见 §9.8；
> 第 13 步做掉了**最后一条**（`/side` 和 `/recap`），见 §9.9——
> §9.6 至此是空的。

> 本文中标注「真 bug」的两条（3.4、3.5）已经在写这份文档时用源码确认过，
> 也都修了：3.4 让一个文件只出一段（`core/instructions.py` 的 `once_per_file()`），
> 3.5 把 http 传输和 `headers` 实现了（`tools/mcp.py`）。两条都有回归测试。
