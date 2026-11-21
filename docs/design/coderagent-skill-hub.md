# 技能市场与网页技能页（设计文档）

> 目标：让技能（skill）不再只能从磁盘手写，而是能从网络下载、在网页上浏览和安装。
> 状态：**三个阶段都已实现**（领域层、网页层、收尾）。§1.1 写的是动手之前的样子。
> 相关：[M4-advanced.md](milestones/M4-advanced.md)（技能机制的来源）、
> [M5-web-interface.md](milestones/M5-web-interface.md)（网页版的地基）、
> [coderagent_skills.md](../usage/coderagent_skills.md)（技能的用户文档）。

---

## 1. 现状与问题

### 1.1 今天有什么

动手之前的样子（技能还在 `extensions/` 里，只能从磁盘读）：

| 能力 | 位置 | 现状 |
|---|---|---|
| 装载技能 | `src/coderagent/extensions/skills.py:78` `load_skills` | 只扫磁盘：用户目录 `~/.coderagent/skills/*/SKILL.md` 与项目目录 `.coderagent/skills/*/SKILL.md` |
| 解析技能 | `src/coderagent/extensions/skills.py:56` `parse_skill` | 读 front matter 的 `name` / `description`，其余是正文 |
| 告诉模型有哪些技能 | `src/coderagent/extensions/skills.py:95` `skill_index` | 一行一个，进 system prompt |
| 模型加载技能 | `src/coderagent/tools/builtin/skill.py:9` `SkillTool` | 给出正文与目录路径 |
| 终端里查看 | `src/coderagent/ui/commands/builtin.py:443` `/skills` | 列出名字、描述、目录 |

### 1.2 缺什么

1. **没有网页入口**。网页版有 `/settings`（`src/coderagent/web/app.py:79`）能改模型配置，技能却只能在终端里 `/skills` 看一眼，
   要用别人写的技能得自己去 GitHub 下载、解压、放到 `~/.coderagent/skills/`、自己确认目录名对不对。
2. **没有来源的概念**。技能没有「从哪来」的记录，也就没有「更新」「来源变了没有」「装的是不是被改过的版本」这些问题的答案。
3. **没有安装的边界**。手工复制没有体积上限、没有文件数上限、没有路径检查，
   一个 zip 里的 `../../.ssh/authorized_keys` 就被复制进了技能目录。

### 1.3 一句话目标

> 技能页面能列出「我能拿到什么」，能下载、能预览、确认之后装到用户目录，并且装进来的东西有据可查。

---

## 2. 范围

### 2.1 做什么

| 编号 | 功能 | 优先级 |
|---|---|---|
| S1 | 三种来源：GitHub 仓库 / 技能注册表（index.json）/ 单个 SKILL.md 直链 | P0 |
| S2 | 下载到暂存区，**预览内容后确认**才安装 | P0 |
| S3 | 只安装到用户目录 `~/.coderagent/skills/` | P0 |
| S4 | 体积、文件数、路径三层沙箱 | P0 |
| S5 | 锁文件：记录来源、版本、逐文件 sha256 | P0 |
| S6 | 独立网页 `/skills`：已装列表、来源输入、预览弹窗、卸载 | P0 |
| S7 | 卸载、更新检查 | P1 |
| S8 | 注册表页面内浏览（填一个 index.json 地址 → 列出技能） | P1 |

### 2.2 不做什么（明确排除）

| 不做 | 理由 |
|---|---|
| 安装到项目目录 `.coderagent/skills/` | 下载物不该进用户的仓库；要进项目由用户自己拷，页面给 `.gitignore` 建议 |
| 任意 zip / tarball 直链 | 无法预先知道里面是什么，路径沙箱的收益被绕过；三种来源已经覆盖常见情形 |
| TUI 里的 `/skills install` | 本轮只做网页；命令行用户仍可手工放置 |
| 在网页里改技能内容 | 技能是包不是文本；改内容属于「作者的事」，用户要改就 fork 上游 |
| 热更新正在跑的会话 | 技能索引烤在 system prompt 里（`src/coderagent/run.py:202`），热更新要重建 `ContextEngine`，代价大于收益（见 §9） |
| 用会话的 `permissions.network` 开关管下载 | 那个开关管的是**模型**跑的命令；网页上的下载是用户自己的动作，语义不同（见 §7.6） |
| 给第三方代码签名 / 校验来源可信度 | 本轮只做到「记录来源 + 校验和 + 让人自己看过」，不做信任链 |

---

## 3. 数据模型

```python
@dataclass(frozen=True)
class Source:
    """Where a skill comes from. One of the three kinds below."""
    kind: str            # "github" | "gitee" | "git" | "registry" | "direct"
    url: str = ""        # the URL to fetch (registry/direct/github tarball)
    repo: str = ""       # "owner/repo" for github and for gitee
    ref: str = ""        # a tag, a branch or a commit
    path: str = ""       # the directory of the skill inside the repository
    name: str = ""       # the name of the skill, when the source names it
```

| 来源 | 用户填的东西 | 内部怎么取 |
|---|---|---|
| `github` | `owner/repo`、`owner/repo@ref`、`owner/repo/skills/pdf-report@v1` | GitHub API 的 tarball：`https://api.github.com/repos/{owner}/{repo}/tarball/{ref}` |
| `gitee` | `gitee:owner/repo`、`gitee:owner/repo/skills/pdf-report` | `git clone --depth 1 https://gitee.com/{owner}/{repo}.git`，再取其中的子目录 |
| `git` | `https://host/org/repo.git`、`git@host:org/repo.git` | `git clone --depth 1` 到临时目录 |
| `registry` | 一个 `index.json` 的地址 | 读 JSON 清单，每条再指向上面三种之一 |
| `direct` | 一个 `SKILL.md` 的地址 | 单文件下载 |

注册表清单的形状（我们自己定的，别人也可以用同样的形状）：

```json
{
  "name": "my registry",
  "skills": [
    {
      "name": "pdf-report",
      "description": "Make a PDF report out of a folder of notes.",
      "source": { "kind": "github", "repo": "owner/repo", "path": "skills/pdf-report", "ref": "v1.2.0" },
      "sha256": "9f2c...（可选，锁定内容）"
    }
  ]
}
```

```python
@dataclass
class Staged:
    """A download that waits for the user to say yes."""
    stage_id: str
    source: Source
    name: str
    description: str
    body: str            # the text of SKILL.md
    files: list[FileEntry]   # path, size, sha256
    sha256: str          # one digest of the whole directory
    warnings: list[str]
    directory: Path      # where it waits (a temporary directory)
```

```python
@dataclass
class FileEntry:
    path: str
    size: int
    sha256: str
```

```python
@dataclass
class Installed:
    """What the lock file knows about an installed skill."""
    name: str
    source: Source
    sha256: str
    installed_at: str
    files: list[FileEntry]
```

锁文件 `~/.coderagent/skills.lock.json`：

```json
{
  "version": 1,
  "skills": {
    "pdf-report": {
      "source": { "kind": "github", "repo": "owner/repo", "path": "skills/pdf-report", "ref": "v1.2.0" },
      "sha256": "…",
      "installed_at": "2026-11-20T10:00:00Z",
      "files": [{ "path": "SKILL.md", "size": 812, "sha256": "…" }]
    }
  }
}
```

`MSWEA_CODER_HOME` 改的是用户目录（`src/coderagent/paths.py:7` `config_home`），锁文件和暂存区也跟着走，测试因此可隔离。

---

## 4. 模块布局

技能从「扩展点」升级成「有供应链的领域」，所以从 `extensions/` 挪到顶层包：

```
src/coderagent/skills/
├── __init__.py    # 现有的 Skill / load_skills / skill_index / parse_skill（搬过来，公共 API 不变）
├── errors.py      # SkillError：给用户看的理由
├── source.py      # Source 的解析（用户填的字符串 → Source）与来源的抓取
├── gitee.py       # Gitee 上的三个站点：清单与它们的 clone 缓存
├── sandbox.py     # 解包的边界：路径、体积、文件数、符号链接
└── install.py     # 暂存、预览、安装、卸载、更新检查、锁文件的读写
```

**改动清单**

| 文件 | 改什么 |
|---|---|
| `src/coderagent/extensions/skills.py` | 删除，内容搬进 `src/coderagent/skills/__init__.py` |
| `src/coderagent/run.py:39,187` | import 改成 `coderagent.skills` |
| `src/coderagent/tools/builtin/skill.py:5` | import 改成 `coderagent.skills` |
| `src/coderagent/ui/commands/builtin.py:444` | import 改成 `coderagent.skills` |
| `tests/coderagent/extensions/test_skills.py` | 挪到 `tests/coderagent/skills/`，import 跟着改 |

**新增**

| 文件 | 职责 |
|---|---|
| `src/coderagent/skills/source.py` | `parse_source(text) -> Source`；`fetch(source, workdir, policy) -> Path`（把来源变成一个目录树）；`fetch_registry(url, policy) -> list[Entry]` |
| `src/coderagent/skills/sandbox.py` | `Policy`（能下多少、能有多大）；`unpack_tar(archive, dest, policy)`；`copy_tree(src, dest, policy)`；`digest(files) -> str`；`check_path` / `check_name` / `sanitize` |
| `src/coderagent/skills/install.py` | `stage(source, policy) -> Staged`；`read_stage(stage_id)`；`install(staged, force=)`；`check_update(installed)`；`uninstall(name)`；`read_lock` / `write_lock` |
| `src/coderagent/skills/gitee.py` | Gitee 上的站点（`SITES`）；`list_skills(site, policy)` 从 clone 里读出清单；clone 的缓存 |
| `src/coderagent/web/skills_api.py` | 网页端点的实现（校验、入参组装、错误翻译）；自带一个 `APIRouter(prefix="/api/skills")` |
| `src/coderagent/web/templates/{en,zh}/skills.html` | 技能页 |
| `tests/coderagent/skills/test_*.py` | 领域层测试 |
| `tests/coderagent/web/test_api_skills.py` | 网页端点测试 |

`skills/__init__.py` 只导出装载相关的东西；下载相关的都在子模块里，
这样「读技能」和「装技能」两件事不会互相牵连。

**实现时与本文档不同的三处**

| 文档写的 | 实现的 | 为什么 |
|---|---|---|
| 名字不合法时「以目录名为准」 | 先把 front matter 的名字收拾干净（转小写、非法字符换成 `-`），收拾不了才用目录名 | 直接用目录名会让一个叫 `SKILL.md` 的直链技能变成 `skill`，而上游明明说了自己叫什么 |
| `Policy` 叫 `Limits` | 叫 `Policy` | 它不止是尺寸，还管「能不能走 http」「哪些主机可以去」 |
| `web/api.py` 挂上 router | `web/app.py` 挂上 router | `skills_api.py` 要用 `api.py` 里的 `require_client`，反过来再 import 就成环了；两个 router 各挂各的更清楚 |

---

## 5. 三种来源怎么取

### 5.1 GitHub 仓库

```
owner/repo                       → ref = 默认分支，path = 整仓里找
owner/repo@main                  → ref = main
owner/repo/skills/pdf-report@v1  → path = skills/pdf-report, ref = v1
```

取法：`GET https://api.github.com/repos/{owner}/{repo}/tarball/{ref}`（`Accept: application/vnd.github+json`），
解 tar.gz。整仓当 skill 的情况只在**根目录就有 `SKILL.md`** 时成立；否则要指 `path`。

API 有速率限制（匿名 60 次/小时）。可配 `skills.github_token` 提高配额；
令牌只用于请求头，**不写进锁文件**。

### 5.2 任意 git 地址

`https://host/org/repo.git` 或 `git@host:org/repo.git` → `git clone --depth 1 --quiet <url> <tmp>`。
机器上没有 `git` 就直接报错（`"git is not installed, so a git URL cannot be used"`），
不给「偷偷用 API 代替」这种惊喜。

clone 出来的是整个仓库，技能是其中的一个子目录，路径由用户指。

### 5.3 注册表（index.json）

一个 JSON 清单（§3 的形状）。清单本身也是一次网络下载，因此同样受 §7 的限制。
清单里的每一条都要能被解析成合法的 `Source`，否则这一条被跳过并在页面上显示原因——
一个坏条目不该让整个清单不可用。

### 5.4 单个 SKILL.md 直链

一次普通下载，得到一个文件。技能名取 front matter 的 `name`，没有就用 URL 的文件名。
直链**不带目录**，所以技能没有脚本和资源——这是它的固有代价，页面上要说清楚。

### 5.5 Gitee 仓库与站点

Gitee 是国内开发者放技能的地方，所以它有自己的来源种类和一组内置站点。

**来源**：`gitee:owner/repo/skills/pdf-report` → `git clone --depth 1 https://gitee.com/{owner}/{repo}.git`，
再取其中的子目录。走 clone 而不是 API，是因为 **Gitee 的 API 对匿名请求放行一阵子就拒绝**
（`403 Forbidden (Rate Limit Exceeded)`），clone 则一直管用。

**站点**：网页上的三个标签页，各对应一个仓库：

| 站点 | 仓库 | 技能 |
|---|---|---|
| `official` | `oschina/gitee-agent-skills` | `mcp-gitee-skills/skills/` 下的 14 个（Gitee 官方，给 Gitee MCP 服务器用） |
| `personal` | `yang_huai_qiang1/agent-skills` | 12 个日常开发用得上的技能 |
| `tools` | `jianchaoteng/agent-skills` | 3 个：两个读代码库，一个管部署 |

站点的清单也从 clone 里读（`src/coderagent/skills/gitee.py`），clone 缓存在
`~/.coderagent/cache/skills/sites/` 里半天。Gitee 上的技能仓库 star 几乎都是 0，
排名靠的是「谁维护 + 有多少技能 + 什么时候更新」，不是 star。

### 5.6 引用的写法

`parse_source(text)` 按前缀分派：

| 输入 | 判定 |
|---|---|
| `github:owner/repo/path@ref` | github |
| `gitee:owner/repo/path` | gitee |
| 长得像 `owner/repo`（含一个 `/`，不是 URL） | github |
| `https://` / `http://` 开头且以 `.json` 结尾 | registry |
| `https://` / `http://` 开头且以 `SKILL.md` 结尾 | direct |
| `https://` / `http://` 开头且以 `.git` 结尾 | git |
| `git@host:...` | git |
| 其它 | 报错，`"this is not a source of a skill: <text>"` |

显式前缀（`github:` / `gitee:` / `git:` / `registry:` / `direct:`）永远优先，用来消歧。

---

## 6. 安装流程

```
用户填来源
   │
   ├─ POST /api/skills/preview   → 下载到暂存区 → 沙箱 → 算 sha256 → 返回预览
   │                                          │
   │                                   用户读 SKILL.md 全文、文件清单、警告
   │                                          │
   │                              POST /api/skills/install（带 stage_id）
   │                                          │
   │                                   落到 ~/.coderagent/skills/<name>/
   │                                   写锁文件
   ▼
新会话里生效
```

### 6.1 暂存

暂存目录：`config_home()/cache/skills/<stage_id>/`，`stage_id` 是随机串。
暂存有 TTL（默认 30 分钟），过期的暂存由安装时顺手清掉（不引入后台清理任务）。

### 6.2 预览返回什么

```json
{
  "stage_id": "…",
  "name": "pdf-report",
  "description": "Make a PDF report out of a folder of notes.",
  "body": "---\nname: pdf-report\n…\n（SKILL.md 的全文）",
  "files": [{"path": "SKILL.md", "size": 812, "sha256": "…"},
            {"path": "scripts/make_report.py", "size": 1204, "sha256": "…"}],
  "sha256": "…",
  "warnings": ["This skill has 1 script. The model may run it with `bash`."]
}
```

**预览是强制的**：没有预览就调不了安装。页面把 `body` 原样显示（`textContent`，不解析 HTML），
文件清单列全，脚本文件单独标出来。

### 6.3 安装

1. 暂存还在吗？不在 → 400 `"the preview is gone, download it again"`。
2. 名字合法吗？`^[a-z0-9][a-z0-9._-]{0,63}$`，不合法 → 400 `"<name> is not a name a skill can have"`。
3. 已经有同名的技能了吗？→ 409 `"<name> is installed already"`，让用户先卸载（不静默覆盖）。
4. 搬进 `config_home()/skills/<name>/`（先写临时目录再 `os.replace`，避免半个技能）。
5. 写锁文件。

### 6.4 卸载

`DELETE /api/skills/{name}` → 删目录 + 删锁文件条目。目录不在锁文件里（用户自己放的）→
403 `"<name> was not installed here, it is yours"`——不删用户手写的技能。

### 6.5 更新检查

`POST /api/skills/update` → 按锁文件里的来源重新抓一次，算新 sha256，和锁文件里的比：
相同 → `"<name> is up to date"`；不同 → 返回新的预览（`stage_id` 复用），用户确认后覆盖安装。
覆盖安装需要显式的 `force: true`，否则 409。

---

## 7. 安全边界

这一节是整个功能里最容易写错的部分，所以逐条写死。

### 7.1 体积与数量

| 限制 | 默认 | 配置键 |
|---|---|---|
| 单次下载总字节 | 8 MiB | `skills.max_bytes` |
| 解包后单文件字节 | 1 MiB | `skills.max_file_bytes` |
| 文件个数 | 2000 | `skills.max_files` |
| 目录深度 | 16 层 | `skills.max_depth` |
| 超时 | 30 秒 | `skills.timeout` |

超限就**中止并清掉暂存**，不留半个文件。下载时按 `Content-Length` 先判一次，
没有长度就边下边数（超过上限就断流）。

### 7.2 路径沙箱

解包 tar/zip 时逐个成员检查：

| 拒绝 | 理由 |
|---|---|
| 绝对路径（`/etc/passwd`） | 逃出目标目录 |
| 含 `..` 的路径 | 逃出目标目录 |
| 符号链接、硬链接 | 指向目标目录外的东西 |
| 设备文件、FIFO、socket | 不是技能该有的东西 |
| 非 UTF-8 名字 | 跨平台会变成乱码 |
| Windows 保留名（`CON`、`NUL`…） | 装完就没法用 |

解出来的每个文件，其最终路径必须落在目标目录内——用 `Path.resolve()` 之后的
`is_relative_to()` 判定，不靠字符串前缀。

### 7.3 名字

技能名 `^[a-z0-9][a-z0-9._-]{0,63}$`。名字同时是目录名，所以要挡住 `..`、斜杠和 Windows 的怪名字。
front matter 里的 `name` 不合法时，**先把它收拾干净**（转小写、非法字符换成 `-`）；
收拾出来还是不能用，才退到目录名，并且给一条警告——不让上游直接决定我们的目录名，
但也不把上游说的名字整个丢掉。

### 7.4 校验和与锁

- 每个文件记 sha256。
- 整个目录算一个 sha256：把 `(相对路径, 文件 sha256)` 排序后拼起来再哈希——与文件系统顺序无关。
- 锁文件记下来；更新检查靠它比对；页面显示它，用户能自己核对。

### 7.5 装进来的东西是「模型会读的文本」

技能不是被执行的可信代码，但它**会被模型读进上下文**，所以：

- 预览页把 `SKILL.md` 全文摊开给人看，这是唯一的防线，不能省。
- 页面明确提示：「安装后模型会看到这份说明，它可以引导模型做什么事」。
- 带脚本的技能单独标出来——脚本由模型用 `bash` 跑，那已经是**会话权限**管的事了，
  安装技能**不**绕过权限层。
- 目录名不能覆盖已有的技能（§6.3 第 3 条），避免「同名顶替」。

### 7.6 网络这一层

- 只允许 `https://`；`http://` 只在用户显式配了 `skills.allow_insecure` 时才放行（明文下载可以改内容）。
- 拒绝 `file://` 和本地路径。
- 解析主机名后，若落在 `127.0.0.0/8`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、
  `169.254.0.0/16`、`::1`、`fc00::/7`，拒绝（不让网页变成探内网的口子）。
  `skills.allowed_hosts` 里的主机名豁免这条检查（测试要连本机的 HTTP 服务，
  用户也可能要连自己机器上的私有服务）。
- 跟随重定向最多 3 跳，每一跳都重新过上面的检查。
- **不用会话的 `permissions.network`**（`src/coderagent/tools/permissions.py:256`）：
  那个开关管的是模型跑的命令，关掉它之后模型不能联网，但用户自己在网页上装个技能是另一回事。
  两件事分开，语义才清楚。

### 7.7 gitignore 建议

安装只写 `~/.coderagent/skills/`，本来就不在仓库里，所以**不需要**改 `.gitignore`。
但用户常会把技能拷进项目，页面在技能详情里给一行建议：

```
# .gitignore
.coderagent/skills/
```

只给建议，不动用户的文件。

---

## 8. 网页

### 8.1 页面

`/skills`，导航栏（`src/coderagent/web/templates/en/base.html`）加一项，和 `Chat` / `Settings` 并列。
中英两套模板（`templates/en/skills.html`、`templates/zh/skills.html`），
文案在 `src/coderagent/web/i18n.py` 的 `STRINGS` 里各加一组键。

页面三块：

```
┌─ 已安装 ────────────────────────────────┐
│ pdf-report    Make a PDF report…   [详情][更新][卸载] │
│ (no skills installed yet)                         │
└───────────────────────────────────────────┘
┌─ 从网络安装 ─────────────────────────────┐
│ [来源__________________________] [下载预览] │
│ 已知注册表： [my registry] [另一个]                   │
└───────────────────────────────────────────┘
┌─ Gitee ──────────────────────────────────┐
│ [oschina/gitee-agent-skills][个人][工具]           │
│ Gitee 官方仓库：驱动 Gitee MCP 服务器的那些技能        │
│ create-issue   Use this skill when…        [下载] │
│ create-pr      Use this skill when…        [下载] │
│ …（每个站点六行）                                │
└───────────────────────────────────────────┘
```

预览弹窗：

```
┌─ 预览：pdf-report ───────────────────────┐
│ 来源  github:owner/repo@v1.2.0            │
│ 大小  3 个文件 / 12.4 KB    sha256 9f2c…  │
│ ⚠ 这个技能有 1 个脚本，模型可以用 bash 跑它  │
│ ┌ SKILL.md ─────────────────────────────┐│
│ │ …全文…                                ││
│ └───────────────────────────────────────┘│
│ 其它文件: scripts/make_report.py (1.2 KB) │
│           [取消]              [安装]      │
└───────────────────────────────────────────┘
```

### 8.2 交互要点

- 下载是**异步**的：点「下载预览」后按钮变灰，出错时把服务端的中文/英文原因显示在输入框下面。
- 安装成功后，已安装列表刷新，并显示一条提示：「新会话里生效」。
- 预览弹窗里的 `SKILL.md` 用 `textContent` 渲染（`app.js` 里没有 `innerHTML` 的用法），
  上游的内容不会变成页面的脚本。
- 中途关掉页面：暂存留在磁盘上，下次进来还在（30 分钟内）；过期自动清。

### 8.3 端点

| 方法 | 路径 | 干什么 |
|---|---|---|
| `GET` | `/api/skills` | 已装的技能（名字、描述、目录、来源、sha256、文件数） |
| `GET` | `/api/skills/sites` | Gitee 上的站点（标签页） |
| `GET` | `/api/skills/sites/{site}` | 某个站点的技能（页面只显示前六个） |
| `GET` | `/api/skills/{name}` | 详情，含 `SKILL.md` 全文与文件清单 |
| `POST` | `/api/skills/preview` | `{source: "owner/repo@v1"}` → 暂存 + 预览 |
| `POST` | `/api/skills/install` | `{stage_id: "…"}` → 装上 |
| `DELETE` | `/api/skills/{name}` | 卸载 |
| `POST` | `/api/skills/update` | `{name: "…"}` → 检查更新，返回新的预览 |
| `POST` | `/api/skills/registry` | `{url: "https://…/index.json"}` → 列出注册表里的技能 |

写操作（`preview` / `install` / `update` / `registry` / `DELETE`）走 `require_client`
（`src/coderagent/web/api.py:44`），和别的写接口一样要 `X-Coder-Client` 头。

下载是阻塞的，所以这几个端点写成同步 `def`（FastAPI 把它们放进线程池），
不要写成 `async def` 里直接 `requests.get`——那会把整个事件循环卡住。

### 8.4 页面之外

终端里的 `/skills` 保持原样，但它现在可以多显示一行来源（终端的输出是英文的）：

```
pdf-report       Make a PDF report out of a folder of notes.
                 ~/.coderagent/skills/pdf-report
                 from owner/repo/skills/pdf-report@v1.2.0 (sha256 9f2cabc123)
```

这一行只在锁文件里有这个技能时才有——自己放进去的技能没有来源。

---

## 9. 生效时机

技能索引在 `build_loop` 时算好，一份进 system prompt（`src/coderagent/run.py:202`），
一份进 `SkillTool`（`src/coderagent/run.py:284`）。所以：

| 情况 | 生效 |
|---|---|
| 网页装完，**新**会话 | 立即生效 |
| 网页装完，**正在跑**的会话 | 不生效 |
| 网页装完，TUI 的 `/skills` | 立即生效（它每次现读，`src/coderagent/ui/commands/builtin.py:446`） |

跑着的会话要生效就得重建 `ContextEngine`（system prompt 在那儿），
和 `/clear`、`/resume` 是一回事的代价。本轮不做，页面上写清楚「新会话里生效」。

---

## 10. 配置

`config/schema.py` 里加一段（`SkillsConfig`）：

```yaml
skills:
  enabled: true
  max_bytes: 8388608
  max_file_bytes: 1048576
  max_files: 2000
  max_depth: 16
  timeout: 30
  registries: []           # 预置的 index.json 地址
  github_token: ""        # 可选，只用于请求头
  allow_insecure: false   # 允许 http://
  allowed_hosts: []       # 豁免私有网段检查的主机名
```

这一段属于**用户层**：可信的层写错 → 当场拒绝（和其它配置一样，`extra="forbid"` + 词表校验）；
项目层写错 → 逐键丢掉（`config/loader.py` 的 `_sanitized()`）。

`enabled: false` 时网页上的写操作一律回 403（「配置里把技能关掉了」），
但已经在磁盘上的技能照常被 agent 读到——这个开关管的是「装」，不是「用」。

`github_token` 是密钥，别写进项目层的配置文件——页面不显示它，只显示「已配置」。

---

## 11. 失败模式

| 情况 | 状态码 | 页面上的话 |
|---|---|---|
| 来源字符串看不懂 | 400 | `这不是一个技能的来源：<text>` |
| 网络不通 / 404 | 400 | `下载失败：<原因>` |
| 超过体积上限 | 400 | `下载太大：超过 8.0 MB 上限` |
| 解包时路径越界 | 400 | `这个包里有越界的路径，已拒绝` |
| 名字不合法 | 400 | `<name> 不是技能能有的名字` |
| 同名已装 | 409 | `<name> 已经装过了` |
| 暂存过期 | 400 | `预览已经过期，请重新下载` |
| 强装但没 force | 409 | `要用 force=true 才能覆盖` |
| 卸载一个不是这里装的 | 403 | `<name> 不是这里装的，是你自己的` |

服务端不把内部异常直接抛给页面：`requests` 的异常翻译成「下载失败：<原因>」，
栈留在日志里。

领域层说的是英语，页面上的话是中文——翻译在 `web/skills_api.py` 的 `REASONS` 表里，
按错误消息里的关键词找一句对应的话。找不到就退回英语原文，不丢信息。

---

## 12. 测试计划

| 层 | 测什么 | 例子 |
|---|---|---|
| `skills/source.py` | 来源解析 | `owner/repo@v1` → github；`https://…/index.json` → registry；`git@host:…` → git；`hello` → 报错 |
| `skills/sandbox.py` | 路径与体积 | tar 里有 `../evil` → 拒绝；有符号链接 → 拒绝；超文件数 → 拒绝；体积上限 → 拒绝；正常包 → 文件清单与 sha256 稳定 |
| `skills/install.py` | 暂存/安装/卸载/锁 | 装完目录里有 SKILL.md、锁文件有条目；卸载后目录与条目都没了；手写的技能卸载被拒；同名安装报冲突 |
| `web` 端点 | 契约 | `preview` 返回预览；`install` 没有 `stage_id` → 400；`install` 过期 `stage_id` → 400；写操作没有 `X-Coder-Client` → 403 |
| `web` 页面 | 渲染 | 页面能出；有 i18n 键缺一个就报错（`tests/coderagent/web/test_i18n.py` 已经在查这个） |

不 mock 网络：`file://` 被 §7.6 拒绝，所以测试起一个真的本地 `http.server` 喂假包，
配置里给 `skills.allow_insecure: true` 和 `skills.allowed_hosts: ["127.0.0.1"]` 放行。
按仓库规矩，**不 mock 没被要求的东西**。

---

## 13. 任务清单

### 阶段 A：领域层 —— 已完成

- [x] 建 `src/coderagent/skills/` 包，把 `extensions/skills.py` 搬进去，改 4 处 import
- [x] `source.py`：`parse_source`、github / git / registry / direct 四种抓取
- [x] `sandbox.py`：解包与拷贝的边界检查、体积/文件数/深度限制、`digest`
- [x] `install.py`：`stage` / `read_stage` / `install` / `check_update` / `uninstall` / 锁文件读写
- [x] `config/schema.py` 加 `SkillsConfig`，`defaults.yaml` 补默认值
- [x] 测试：`tests/coderagent/skills/`（64 个）

### 阶段 B：网页层 —— 已完成

- [x] `web/skills_api.py`：端点实现与错误翻译（领域层说英文，这里翻译成访问者的语言）
- [x] `web/app.py` 挂上 router，`/skills` 页面
- [x] `templates/{en,zh}/skills.html`，`base.html` 导航加一项
- [x] `static/app.js`：已装列表、来源输入、预览弹窗
- [x] `web/i18n.py`：中英文案
- [x] 测试：`tests/coderagent/web/test_api_skills.py`（21 个）

### 阶段 C：收尾 —— 已完成

- [x] usage 文档：`docs/usage/coderagent_skills.md` 加「从网络安装」一节（英文）
- [x] 中文 usage 文档：`docs/usage/coderagent_skills_zh.md`（新建，两版对齐）
- [x] `docs/design/README.md` 索引加这一篇
- [x] 终端 `/skills` 显示来源
- [x] `pytest tests/coderagent` 全绿

### 阶段 D：Gitee 站点 —— 已完成

- [x] `source.py` 加 `gitee` 这一种来源：`gitee:owner/repo/path`，靠 clone 取
- [x] `skills/gitee.py`：三个站点、清单、clone 的缓存
- [x] `web/skills_api.py`：`GET /api/skills/sites`、`GET /api/skills/sites/{site}`
- [x] 技能页加标签页，每个站点显示六行，点一个就下载
- [x] 中英文案、usage 文档、设计文档
- [x] 测试：`tests/coderagent/skills/test_gitee.py`、`web/test_api_skills.py` 加 3 个

---

## 14. 风险与取舍

| 风险 | 现在的判断 |
|---|---|
| 供应链投毒：上游改了 skill 内容 | 锁文件记 sha256，更新时内容变了会重新走预览；用户能自己核对哈希。**没有**签名，所以「上游被攻破」防不住 |
| 提示注入：`SKILL.md` 里写「忽略之前的指令」 | 技能是模型主动加载的文本，注入风险真实存在。缓解是「预览给人看」+ 索引里只有一行描述。真要根治得让模型加载时也标记来源，那属于上下文治理的活儿，不在本轮 |
| SSRF：网页被拿来探内网 | §7.6 的地址检查 + 只允许 https + 令牌只用于请求头 |
| 半安装：下载中途断 | 先暂存、后搬；搬用 `os.replace`；失败清暂存 |
| 速率限制：GitHub API 匿名配额 | `skills.github_token` 可配；错误消息说清楚是配额问题 |
| 生态碎片：注册表格式没人用 | 格式是我们定的，但 JSON 足够通用；`parse_source` 也允许用户直接贴仓库地址，不依赖注册表 |
| 与上游 agent 的技能格式不一致 | 本轮不追（`SKILL.md` + front matter 是 Anthropic 的常见做法），只在文档里说明差异 |
