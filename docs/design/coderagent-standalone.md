# 去掉 mini-swe-agent 的核心模块：分析与取舍

> 这份文档回答一个问题：**能不能把 `src/minisweagent/` 从这个仓库里拿掉，把 `coderagent` 变成一个
> 独立的项目？**
>
> 结论先行：**能，而且代价不大——但「拿掉」和「重写」是两件事，前者便宜，后者不划算。**
> 真正需要重写的只有两块：远程沙箱（6 种 environment）和 benchmark harness（SWE-bench / ProgramBench）；
> coderagent 现在从 mini 借的那 311 行代码，原样搬过来比重写更好。
>
> 代码位置：`src/minisweagent/`（59 个 Python 文件，5357 行）、`src/coderagent/`（115 个文件，18758 行）。
> 文中每条结论都能在源码里找到出处，引用格式是 `文件:行号`。

---

## 目录

1. [结论](#verdict)
2. [现状：事实清单](#facts)
3. [三个方案](#options)
4. [利弊对照](#tradeoffs)
5. [风险清单](#risks)
6. [迁移路线](#plan)
7. [需要拍板的问题](#questions)
8. [附录 A：coderagent 借用的接口清单](#appendix-a)
9. [附录 B：搬和重写的成本](#appendix-b)

---

## 结论 {#verdict}

1. **技术上可行**：coderagent 对 mini 的依赖面窄得出奇——9 处 import、6 个模块、311 行。
   删掉 mini 之后，coderagent 仍然是完整的（`coder` CLI、TUI、网页版、eval harness 都齐）。
2. **「重写」不划算**：那 311 行（`LocalEnvironment`、`get_config_from_spec`、`recursive_merge`、
   `set_cache_control`、`retry`、`FormatError`）每一行都有测试、有注释、已经被两个项目验证过。
   重写只会引入回归，应该**原样搬**（复制 + 改 import），把「重写」留给真正没有替代品的两块。
3. **真正贵的是两块**：
   - **远程沙箱**：6 种 environment（docker / singularity / swerex_docker / swerex_modal /
     bubblewrap / contree）背后是 SWE-ReX、Modal、contree-sdk 三套外部依赖。搬 = 复制代码 +
     搬依赖；重写 = 重新实现远程命令执行协议。
   - **benchmark harness**：`run/benchmarks/swebench.py` 等依赖 `datasets` 下载数据集，是这个仓库
     作为「刷 SWE-bench 榜的 agent」的立身之本。删掉 = 放弃这条身份。
4. **有一处隐式依赖必须先补**：全局 `.env` 是靠 `minisweagent/__init__.py` 的 import 副作用加载的
   （`src/minisweagent/__init__.py:36`）。今天 `coder` 能读到 `~/.config/mini-swe-agent/.env` 里的
   API key，全靠这一行。删掉 mini 之前必须自己实现（见 [P0-1](#p0-1)）。
5. **建议**：走 [方案 B](#option-b)（切断依赖、不删包），把 mini 降级成「可选的兼容层」。
   等文档、CI、发布流水线都改顺了，再决定要不要物理删除（[方案 A](#option-a)）。

---

## 现状：事实清单 {#facts}

### 规模

| | 文件数 | 行数 | 测试 |
|---|---|---|---|
| `src/minisweagent/` | 59 | 5357 | `tests/{agents,models,environments,config,run,utils}` 共 46 文件 / 9273 行 |
| `src/coderagent/` | 115 | 18758 | `tests/coderagent/` 共 110 文件 / 16986 行 |

coderagent 已经是 mini 的 3.5 倍大。mini 现在更像一个「被借用的工具箱」，而不是这个仓库的主体。

### coderagent 到底借了什么 {#borrowed}

9 处 import，落在 6 个模块上：

| 被借的东西 | 定义处 | 行数 | 谁在用 |
|---|---|---|---|
| `LocalEnvironment` | `src/minisweagent/environments/local.py:19` | 98 | `core/loop.py:23`、`core/sandbox.py:37`、`tools/builtin/shell.py:17`（`CodingEnvironment` 的父类）、`run.py:55` |
| `get_config_from_spec` | `src/minisweagent/config/__init__.py:56` | 64 | `config/loader.py:13`、`eval/task.py:14` |
| `recursive_merge` | `src/minisweagent/utils/serialize.py` | 29 | `config/loader.py:14`、`eval/runner.py:23` |
| `set_cache_control` | `src/minisweagent/models/utils/cache_control.py` | 67 | `models/backends.py:13` |
| `retry` | `src/minisweagent/models/utils/retry.py` | 27 | `models/backends.py:14` |
| `FormatError` | `src/minisweagent/exceptions.py` | 26 | `models/streaming.py:12` |

合计 311 行，加 `environments/__init__.py:30` 的 `get_environment` 注册表，一共 344 行。

**注意**：`core/sandbox.py:37` 用的 `get_environment` 会把 mini 的 7 种 environment 全部拉进来，
这是 coderagent **唯一一处真正吃下 mini 的大功能**的地方（见 [方案 A](#option-a) 的成本）。

### 一处隐式依赖：全局 .env {#dotenv}

`src/minisweagent/__init__.py` 在 import 时做了三件事：

- `__init__.py:31` 打印版本横幅（`coderagent/__init__.py:11` 用 `MSWEA_SILENT_STARTUP` 把它关掉了）；
- `__init__.py:36` `dotenv.load_dotenv(dotenv_path=global_config_file)` 加载
  `user_config_dir("mini-swe-agent")/.env`；
- `__init__.py:11` 定义 `__version__`（第 2 步之后，`pyproject.toml` 的 `dynamic version`
  指向的是 `coderagent/version.py`，不再指向它）。

第 2 条是**功能性的**：provider 的 API key 走 `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` 这类环境变量，
环境变量来自这个 `.env`。搬 import 之前，`coder` 能用上它，是因为 `config/loader.py:13` 顶层 import 了
`minisweagent.config`，顺带把父包 `minisweagent/__init__.py` 跑了一遍；
第 1 步之后由 `coderagent/paths.py:load_global_env()` 接手（见[第 1 步](#step-1)）。

**如果只把 9 处 import 改掉而不补这一条，用户会突然发现 key 读不到了，而且没有任何报错**——
表现是「认证失败」或者更糟：中转站返 500，模型重试 10 次之后才放弃。

### mini 提供了、coderagent 没有的东西 {#mini-only}

| 能力 | 位置 | coderagent 有替代吗 |
|---|---|---|
| 远程沙箱 6 种 | `environments/extra/*.py`、`environments/{docker,singularity}.py` | 没有。`coderagent/core/sandbox.py:36` 直接复用 |
| `mini` / `mini-swe-agent` CLI | `run/mini.py` | 没有。`coder` 是另一个东西 |
| SWE-bench / ProgramBench runner | `run/benchmarks/*.py` | 没有。`coderagent/eval/` 是自己的任务集 harness，跑不了 SWE-bench |
| Inspector | `run/utilities/inspector.py` | 没有 |
| Textbased 模型（不吐 tool call，用文本解析动作） | `models/litellm_textbased_model.py` 等 | 没有。coderagent 全靠 tool call |
| 协议定义（Model / Environment / Agent） | `minisweagent/__init__.py:43-79` | 有自己的 `core/protocols.py` |

### 文档与 CI 的牵连 {#docs-ci}

- `docs/reference/` 28 页全部是 mini 的 API 文档；`docs/usage/{mini,swebench,programbench,inspector}.md`
  和 `docs/advanced/`、`docs/models/` 是 mini 的使用文档。合计约 2800 行。
- `mkdocs.yml:66-95` 的 nav 里，mini 的条目和 coderagent 的条目是**平级**的两段。
- `.github/workflows/pylint.yaml:33` 只 lint `minisweagent/`——删掉之后这个 workflow 就没内容可查了。
- `.github/workflows/release.yaml` 用 `grep` 取版本号（第 2 步之后取的是 `src/coderagent/version.py`）；
  冒烟测试跑的是 `pipx run mini-swe-agent --help`（装的是上游的包）。
- `.github/bump_version.py` 第 2 步之后指向 `src/coderagent/version.py`。

---

## 三个方案 {#options}

### 方案 A：物理删除 {#option-a}

删掉 `src/minisweagent/`、`tests/{agents,models,environments,config,run,utils}`、mini 的文档页；
把 311 行搬到 `coderagent/` 下；重写或丢弃远程沙箱与 benchmark。

**得到**

- 仓库只剩一个项目、一个包、一个 CLI、一个心智模型。文档和代码一一对应。
- 依赖变轻：`datasets`、`openai`、`prompt_toolkit`、`tenacity`、`python-dotenv`、`platformdirs`
  都可以摘掉（`rich`/`typer` 要留，`typer` 自己带 `rich`）。`datasets` 尤其重（带 pyarrow）。
- 不再有「这个仓库到底是 mini 还是 coder」的困惑；`coderagent/__init__.py:1` 那句
  「built on top of mini-swe-agent's reusable primitives」也就过时了。
- 沙箱类型由自己定义，可以按 coding agent 的需要重做（现在 mini 的 environment 是为
  「一个动作 → 一段输出」设计的，coding agent 需要「可取消的进程组 + 取消检查」，这些已经在
  `tools/builtin/shell.py:37` 的 `execute_cancellable` 里自己写了一遍）。

**失去**

- 6 种远程沙箱（除非一起搬）。
- SWE-bench / ProgramBench 的跑分能力（`datasets` 数据集下载 + runner）。
- `mini` CLI 和 Textbased 模型。
- 28 页 reference 文档 + mini 的 usage 文档（约 2800 行）要删掉或改写。
- **上游关系**：这个仓库是 mini-swe-agent 的 fork，删掉核心之后就不再是 mini 的下游，
  以后 upstream 的修复要自己拿。

**风险**：见 [风险清单](#risks)。最贵的三条是 `.env`、发布流水线、SWE-bench 身份。

**工作量估计**：搬 311 行约 0.5 天；`.env` + version + pyproject + CI 约 1 天；
沙箱层二选一（搬 or 删）约 1–3 天；文档与 nav 清理约 1–2 天；整体 3–7 天。

### 方案 B：切断依赖，保留 mini {#option-b}

`src/minisweagent/` 原样留着，但 coderagent 不再 import 它：把借用的 311 行搬进
`coderagent/compat/`（或 `coderagent/_vendor/`），自己加载 `.env`，自己定义 version。
mini 变成一个**只有 `mini` CLI 还在用**的独立包。

**得到**

- coderagent 与 mini 之间**零 import**：以后删不删 mini 都不影响 coderagent，
  是一个提交就能完成的「以后再说」。
- 依赖仍然不轻（mini 还在树里），但 `coder` 的**运行时**不再需要 mini 的那套 import。
- 文档、CI、发布流水线一行都不用改——mini 还是 mini。

**失去**

- 仓库里仍然有两套 agent、两套文档，读者还是会问「这两个是什么关系」。
- 依赖没变轻（`datasets` 还在）。

**工作量估计**：0.5–1 天。

### 方案 C：维持现状 {#option-c}

继续 import mini 的 311 行。

**得到**：零工作量。

**失去**：

- `coderagent` 的「独立」是假的：删掉 mini 就崩。
- mini 的 `__init__.py` 每次 import 都跑（打印横幅被关了，但 `dotenv.load_dotenv` 还在跑）。
- 6 种沙箱和 mini 绑死在一起——想改 environment 的接口，就得改 mini 的。

**什么时候选它**：如果目标只是「让 coderagent 的代码更干净」，那把借用的东西整理成
`coderagent/compat/`（方案 B 的第一步）就够了，剩下的可以不急。

---

## 利弊对照 {#tradeoffs}

| 维度 | A：物理删除 | B：切断依赖 | C：现状 |
|---|---|---|---|
| coderagent 独立 | 是 | 是 | 否 |
| 仓库只有一个项目 | 是 | 否（两套并存） | 否 |
| 依赖变轻（摘掉 `datasets` 等） | 是 | 否 | 否 |
| 保留 SWE-bench 跑分 | 否 | 是 | 是 |
| 保留 6 种远程沙箱 | 需额外搬 | 是（继续 import mini 的话） | 是 |
| 文档工作量 | 大（删/改约 2800 行） | 小 | 无 |
| CI / 发布流水线改动 | 大（pylint、release、bump_version） | 无 | 无 |
| 失去上游同步 | 是 | 否 | 否 |
| 工作量 | 3–7 天 | 0.5–1 天 | 0 |
| 回归风险 | 中（沙箱、config、env 三处） | 低 | 无 |

---

## 风险清单 {#risks}

### P0-1：全局 .env 静默消失 {#p0-1}

**现象**：删掉 mini 后，用户 `~/.config/mini-swe-agent/.env`（macOS 上是
`~/Library/Application Support/mini-swe-agent/.env`）里的 key 不再生效。
**没有报错**，只是认证失败或模型重试 10 次后放弃。
**对策**：在 `coderagent/paths.py` 旁边加一个自己的 `.env` 加载，路径保持不变（兼容老用户），
或者改到 `~/.coderagent/.env` 并同时读两个（老路径优先）。**这一步必须在删包之前做完并有测试。**
（第 1 步已经做完了：`coderagent/paths.py:load_global_env()`，
测试在 `tests/coderagent/test_paths.py`。）

### P0-2：发布流水线与包名 {#p0-2}

- `pyproject.toml:7` 的 `name = "mini-swe-agent"` 决定了 PyPI 上的包名。删掉 mini 核心之后，
  这个名字和内容对不上。
- `pyproject.toml` 的 `version = {attr = ...}` 原来指向 `minisweagent.__version__`，
  删掉 mini 就会失效——第 2 步已经改成指向 `coderagent.version.__version__`。
- `.github/workflows/release.yaml` 用 `grep` 读版本号的位置（第 2 步已改），
  冒烟测试跑 `pipx run mini-swe-agent --help`（装的是上游的包，没测我们的产物）。
- **取舍**：PyPI 上的 `mini-swe-agent` 是上游 SWE-agent/mini-swe-agent 的名字，**不能占**。
  要么保持 `mini-swe-agent` 这个名字（和上游冲突，不建议），要么换名（`coderagent`？需要查重名），
  要么不发 PyPI、只发 GitHub release。
- **对策**：改名前先确认发布方式；这一步会让 CI 多跑几轮。

### P0-3：SWE-bench 身份 {#p0-3}

`run/benchmarks/swebench.py:222` 用 `datasets` 下载数据集，runner 里还有实例镜像、patch 提取、
报告生成。删掉它 = 这个仓库不能再宣称「能跑 SWE-bench」。
**注意**：coderagent 自己的 eval harness（`coderagent/eval/`、`evals/`）**替代不了**它——
那是一套自己的任务集（8 个任务 + 离线套件），不是 SWE-bench 的 3000 个实例。

### P1-1：远程沙箱 {#p1-1}

`core/sandbox.py:36-47` 直接用 mini 的 `get_environment`。方案 A 下要么：

- **搬**：`environments/{docker,singularity}.py` + `environments/extra/*`（约 6 个文件），
  连同 `swe-rex`、`modal`、`contree-sdk` 三个依赖一起搬进 coderagent 的 extras；
- **删**：只留 local 沙箱，`sandbox.type` 的文档、`coderagent_sandbox.md` 中英两版都要改。

`coderagent/core/sandbox.py:43` 还用 `_check_finished` 打补丁把 mini 的
「命令打印哨兵字符串就算完成」的语义关掉——搬过去时要保留这个补丁逻辑。

### P1-2：isinstance 判断的语义 {#p1-2}

`LocalEnvironment` 在 coderagent 里被当成「本地环境」的判据用了 6 处
（`run.py:136`、`run.py:190`、`shell.py:208`、`shell.py:245`、`sandbox.py:41`、`loop.py:497`）。
换了基类之后，这些判断要跟着改，否则远程环境会被当成本地环境，cwd 传错。

### P1-3：文档与 nav {#p1-3}

`docs/reference/` 28 页 + `docs/usage/{mini,swebench,programbench,inspector}.md` +
`docs/advanced/` + `docs/models/` 都是 mini 的。`mkdocs.yml` 的 nav 里 mini 和 coderagent
是两段平级条目。删掉要动 nav（`mkdocs build --strict` 会检查死链），
还要决定这些页面是删掉、还是改成「历史文档」留在 `docs/` 外面。

### P1-4：pylint workflow {#p1-4}

`.github/workflows/pylint.yaml:33` 只 lint `minisweagent/`。删掉之后要么改指 `coderagent/`，
要么这个 workflow 就没意义了。**coderagent 目前没有进 pylint 的检查范围**——搬代码时正好补上。

### P2-1：依赖瘦身的前提 {#p2-1}

| 依赖 | 谁在用 | 能不能摘 |
|---|---|---|
| `datasets` | mini 的 swebench runner | 删掉 mini 才能摘 |
| `openai` | mini 的 multimodal | 同上 |
| `prompt_toolkit` | mini 的 interactive agent | 同上 |
| `tenacity` | `models/utils/retry.py`（coderagent 在用） | 要么留，要么自己写 20 行重试 |
| `python-dotenv` | `minisweagent/__init__.py:36`（功能） | 自己实现加载，或留 |
| `platformdirs` | `minisweagent/__init__.py:27` | coderagent 的 `paths.py` 用 `Path.home()`，可直接摘 |
| `rich` | typer 的输出 | 留（typer 自带） |
| `jinja2` / `fastapi` / `textual` / `typer` / `pydantic` / `litellm` / `yaml` / `requests` | coderagent 在用 | 留 |

### P2-2：版本号与 bump 脚本 {#p2-2}

原来 `pyproject.toml` 和 `.github/bump_version.py` 都指向 `src/minisweagent/__init__.py`，
而 coderagent 自己的 `__version__` 是**手写**的、没进发布流程。
第 2 步（[第 2 步](#step-2)）定了：**版本源是 `src/coderagent/version.py`**，
发行包的版本号跟 coding agent 走；mini 保留自己的 `2.4.6`，那只是 mini 代码的版本。

---

## 迁移路线 {#plan}

分 5 步，每步一个提交，每步都能独立通过测试和 CI。**第 4 步之前，仓库里一直有 mini**，
所以任何一步都能停下来。

### 第 0 步：加一道闸（半天） {#step-0}

把 coderagent 对 mini 的 9 处 import 收敛到一个模块，比如
`coderagent/compat/__init__.py`，让「coderagent 依赖 mini」这件事变成**一个文件**里的决定。
此时行为不变，但边界清楚了。

**验收**：`grep -rn "minisweagent" src/coderagent/` 只剩一个文件。

### 第 1 步：搬 311 行（半天）—— ✅ 已做（2026-11-26） {#step-1}

把 6 个模块复制进 `coderagent/compat/`，改 import，**不改逻辑**。
`LocalEnvironment` 的子类关系保留（`CodingEnvironment` 照旧继承它）。

**两处和计划不一样的地方**：

1. **`isinstance` 的判断没有换成新基类，换成了 `is_local()`**（`compat/environments.py`）。
   原来那 6 处 `isinstance(environment, LocalEnvironment)` 判断的是「这个环境在本机跑命令吗」，
   而 mini 的 `LocalEnvironment` 也可以被点名（`sandbox.type` 支持点号路径，
   `tests/coderagent/core/test_sandbox.py` 就这么用）。换了类之后，那种环境会被误判成远程的。
   现在的判据是「有没有 `env_override`」：本机的环境有，mini 的 6 种远程沙箱都没有。

2. **`.env` 的加载跟着一起做了**（原计划的第 2 步的一半）。搬完 import 之后，
   `coderagent` 不再 import `minisweagent`，那个 import 时的副作用
   （`minisweagent/__init__.py:36` 的 `dotenv.load_dotenv`）就没了——
   **用户的 key 会静默地读不到**。所以 `coderagent/paths.py` 加了 `load_global_env()`，
   在 `coderagent/__init__.py` 里调用：读 `~/.coderagent/.env` 和 mini 的老路径
   `user_config_dir("mini-swe-agent")/.env`，环境里已有的值优先，coding agent 的文件优先于 mini 的。

**验收**：`pytest tests/coderagent -q` 全绿（1468 passed）；`grep -rn "minisweagent" src/coderagent/`
只剩 `core/sandbox.py` 的远程沙箱注册表；`tests/coderagent/compat/` 和 `tests/coderagent/test_paths.py`
是这一轮新增的测试。

### 第 2 步：版本号（半天）—— ✅ 已做（2026-11-26） {#step-2}

- `pyproject.toml` 的 `dynamic version` 改成指向 `coderagent.version.__version__`，
  `.github/bump_version.py` 同步改。
- （`.env` 的部分已经在第 1 步做完了。）

**两处和计划不一样的地方**：

1. **版本号放在自己的模块里**（`src/coderagent/version.py`），而不是 `coderagent/__init__.py`。
   原因：构建时的 `attr:` 要读这个值，`coderagent/__init__.py` 会 import 整个包
   （`core.protocols` → pydantic），构建环境里没有这些依赖。`version.py` 只有一个赋值，
   setuptools 读它不用 import 任何东西。

2. **mini 的 `__version__ = "2.4.6"` 留着**。它是 mini 自己的版本（横幅和
   `agents/default.py:173` 的 `mini_version` 都用它），跟这个仓库发布的是两件事。
   但发布流水线现在只认 coding agent 的版本号：release.yaml 的校验改成 grep
   `src/coderagent/version.py`。

**后果**：这个仓库的发行包版本号现在是 `0.1.0`（coding agent 的），
而 PyPI 上 `mini-swe-agent` 这个名字是上游的——包名的事仍然留在第 4 步
（[P0-2](#p0-2)）。冒烟测试还在跑 `pipx run mini-swe-agent --help`，
它装的是**上游**的包，不是我们的产物；改它要等包名定了。

**验收**：`uv build --wheel` 出来的包是 `mini_swe_agent-0.1.0-py3-none-any.whl`。

### 第 3 步：决定沙箱层（1–3 天） {#step-3}

三选一：

- **搬**：把 mini 的 environment 复制进 `coderagent/sandbox/`（新名字，避免和
  `core/os_sandbox.py` 混淆），`swe-rex` / `modal` / `contree-sdk` 变成 coderagent 的 extras。
- **留**：coderagent 声明 `mini-swe-agent` 为**可选依赖**（`pip install coderagent[sandbox]`），
  `core/sandbox.py` 改成 try-import。这是方案 B 的终态。
- **删**：只保留 local 沙箱，改 `sandbox.type` 的文档。

**验收**：`tests/coderagent/core/test_sandbox.py` 里现有的沙箱测试全绿（不 mock）。

### 第 4 步：删包 + 收尾（1–2 天） {#step-4}

删 `src/minisweagent/` 和 mini 的测试、文档；改 `mkdocs.yml` 的 nav；
改 `pylint.yaml` 指向 `coderagent/`；处理 PyPI 包名（[P0-2](#p0-2)）。

**验收**：`uv sync --locked --extra full && uv run --locked --extra full pytest -q` 全绿；
`ruff check src tests`、`ruff format --check src tests` 干净；`mkdocs build --strict` 无死链；
四个 workflow 绿。

---

## 需要拍板的问题 {#questions}

> 第 1 步做完后，「远程沙箱」这个问题更急了一点：`core/sandbox.py` 现在是 coderagent 里
> **唯一**还 import mini 的地方，它决定了 `sandbox.type` 能不能用 docker / swerex / bubblewrap。

1. **SWE-bench 还跑不跑？** 如果要跑，mini 的 `run/benchmarks/` 和 `datasets` 依赖必须留着
   （[方案 B](#option-b) 或「搬但不删」）。如果这个仓库以后只做 coding agent，
   那就该删——但要接受失去刷榜能力。
2. **远程沙箱保留几种？** 全搬（要 `swe-rex`/`modal`/`contree-sdk`）、只搬 docker/singularity、
   还是只留 local？这决定了第 3 步的工作量。
3. **包名怎么办？** `mini-swe-agent` 是上游的名字，不能占。是改名发 PyPI，还是只发 GitHub release？
4. **mini 的历史文档留不留？** 删掉就干净，但 `docs/reference/` 28 页是一次性的沉没成本；
   也可以移到 `docs/legacy/` 之外（不进 nav）。
5. **`.env` 的新位置？** 保持 `~/.config/mini-swe-agent/.env`（兼容，但名字和项目不符），
   还是改成 `~/.coderagent/.env`（干净，但要兼容读旧的）？

---

## 附录 A：coderagent 借用的接口清单 {#appendix-a}

搬的时候照这张表签收。左边是现在用的，右边是要落地的。

### A.1 `LocalEnvironment`（98 行）

| 成员 | coderagent 怎么用 | 备注 |
|---|---|---|
| `__init__(config_class=..., **kwargs)` | `shell.py:27` 的 `CodingEnvironment` 继承它 | 需要 `config_class` 这个钩子 |
| `config.cwd` | `sandbox.py:41`、`shell.py:208`、`loop.py:497` | `cwd` 是相对/绝对路径，由调用方给 |
| `environment()` | `shell.py` 的 `execute_cancellable` 用 | 合并 `os.environ` 和 `config.env` |
| `execute(action, cwd, timeout=)` | `shell.py` 覆盖了它 | coding agent 用的是 `execute_cancellable` |
| `_check_finished(output)` | `sandbox.py:43` 用猴补丁关掉它；`shell.py:34` 覆盖它 | mini 的「哨兵字符串」语义 |
| `get_template_vars()` | `run.py` 拼模板变量 | 传 `platform.uname()` + `os.environ` |

### A.2 `get_config_from_spec`（64 行）

- `config/loader.py:13` 用它解析 `--config key=value` 和 `--config file.yaml`；
- `eval/task.py:14` 用它读任务自带的 `config.yaml`。
- 搜索路径有 5 处：`MSWEA_CONFIG_DIR`、当前目录、包内 `config/`、`config/extra/`、`config/benchmarks/`。
  搬过去时，coderagent 只需要前两个 + 包内 `coderagent/config/`。

### A.3 `recursive_merge`（29 行）

`config/loader.py:14`（配置分层合并）、`eval/runner.py:23`。纯函数，无依赖，直接搬。

### A.4 `set_cache_control`（67 行）

`models/backends.py:13`。处理 Anthropic 的 cache_control 标记；mini 的 `default_end` / `None` 两种模式
（`ephemeral` 会报 `ValueError`，这个坑在 [文档复核] 里修过一次）。

### A.5 `retry`（27 行）

`models/backends.py:14`。tenacity 的薄包装：`MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT` 环境变量控制重试次数
（终端里 `model.max_retries` 不生效，只有 `coder web` 用它）。

### A.6 `FormatError`（26 行）

`models/streaming.py:12`。mini 的 `FormatError` 把细节放在 `messages` 里而不是文本里，
coderagent 的流式解析依赖这个形状（见 `models/streaming.py:26` 的注释）。

---

## 附录 B：搬和重写的成本 {#appendix-b}

| 模块 | 搬（复制） | 重写 | 建议 |
|---|---|---|---|
| `LocalEnvironment` | 30 分钟 | 2 小时（进程组 kill、超时、环境合并都要重新踩坑） | 搬，顺手把 `execute_cancellable` 合并进去 |
| `get_config_from_spec` | 10 分钟 | 1 小时（搜索路径的语义要重新定） | 搬 |
| `recursive_merge` | 5 分钟 | 30 分钟 | 搬 |
| `set_cache_control` | 15 分钟 | 2 小时（Anthropic 的 cache 语义） | 搬 |
| `retry` | 10 分钟 | 1 小时 | 搬；要摘 `tenacity` 就自己写 20 行 |
| `FormatError` | 5 分钟 | 30 分钟（形状变了要改流式解析） | 搬 |
| 6 种远程 environment | 2 小时（复制 + 改 import） | 1–2 周（远程执行协议从零） | 搬，或者留成可选依赖 |
| SWE-bench runner | 2 小时 | 3–5 天 | 搬（如果还要跑榜） |
