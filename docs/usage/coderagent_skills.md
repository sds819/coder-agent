# Skills

> 中文版：[技能](coderagent_skills_zh.md)

A skill is a package of instructions, scripts and resources for a kind of task
that comes back often.

```
.coderagent/skills/pdf-report/
├── SKILL.md
├── scripts/
│   └── make_report.py
└── assets/
    └── template.docx
```

The `SKILL.md` says what the skill is for. The model sees the name and the
description of every skill, and loads the whole one when the description fits
the task:

```markdown
---
name: pdf-report
description: Make a PDF report out of a folder of notes.
---
Run `scripts/make_report.py` to build the report:

    python scripts/make_report.py notes/ --template assets/template.docx

The report lands in `report.pdf`.
```

| Field | What it is | Default |
|---|---|---|
| `name` | The name of the skill | The name of the directory |
| `description` | What it is for, and when to use it | |

The body is the instruction that the model reads when it loads the skill. A
file without a front matter is ignored.

## Where a skill is looked for

| Where | What |
|---|---|
| `.coderagent/skills/*/SKILL.md` | The skills of the project |
| `~/.coderagent/skills/*/SKILL.md` | The skills of the user |

The project comes last, so a project may replace a skill of the user with the
same name. `MSWEA_CODER_HOME` moves the directory of the user.

`/skills` lists them:

```
pdf-report       Make a PDF report out of a folder of notes.
                 /path/to/project/.coderagent/skills/pdf-report
                 from owner/repo/skills/pdf-report@v1.2.0 (sha256 9f2cabc123)
```

The last line is only there for a skill that came from the network: it says where the skill
came from and what its content hashes to.

## How the model uses a skill

The index of the skills goes into the system prompt, so the model knows what
is on the table without paying for it:

```
<skills>
These skills are available. Load one with the `skill` tool when its description fits the task.
- pdf-report: Make a PDF report out of a folder of notes.
</skills>
```

When the task fits, the model calls the `skill` tool with the name. The tool
gives back the body of the `SKILL.md` and the path of the directory, so the
model knows where the scripts are. The scripts themselves are run with
`bash`, in the working directory of the session.

A skill is a package of steps, not a program: the model reads the
instructions and follows them, and the scripts are only there to make the
steps easier.

## Installing a skill from the network

The page `/skills` of the web interface (see
[The web interface](coderagent_web.md)) lists the skills that are installed and
installs new ones from the network.

```
coder web
```

The page has three parts: **Installed** — every skill in `~/.coderagent/skills/`
with its source and its digest — **Install from the network**, a field for
a source and a button that downloads it and shows what it is, and the tabs of
the sites of Gitee. A skill you put there yourself has no source, and the page
says so.

Nothing is written to the disk before you have read it: the download waits in
the cache and the page shows it first.

### The sites of Gitee

The tabs under the field are the three sites on Gitee that hold real skills:

| Tab | What it is |
|---|---|
| `oschina/gitee-agent-skills` | the repository of Gitee itself: fourteen skills that drive the Gitee MCP server |
| `yang_huai_qiang1/agent-skills` | a personal collection: twelve skills for everyday work |
| `jianchaoteng/agent-skills` | three skills: two for reading a codebase, one for deployment |

A tab shows six skills at a time. Every skill of the site is fetched, and the
pager under the cards walks through them. A click on a skill downloads it
and opens the same dialog as any other download, so you still read it before it
is installed.

The list of a site is read from a clone of its repository, and the clone is
kept in `~/.coderagent/cache/skills/sites/` for half a day: the API of Gitee
lets anonymous callers in for a while and then refuses them, but a clone
always works. The **Sync** button at the top of the tab throws the clone away
and fetches the site again, so you see what the site holds now.

### The sources

| What you write | What it is |
|---|---|
| `owner/repo` | a GitHub repository, the default branch |
| `owner/repo@v1.2.0` | a GitHub repository at a tag, a branch or a commit |
| `owner/repo/skills/pdf-report@v1` | one skill of a GitHub repository |
| `gitee:owner/repo/skills/pdf-report` | one skill of a repository of Gitee |
| `https://host/org/repo.git`, `git@host:org/repo.git` | a git repository |
| `https://example.com/skills/pdf-report/SKILL.md` | one file |
| `https://example.com/index.json` | a registry: a list of skills |

A prefix says what you mean when an address could be read in two ways:
`github:`, `gitee:`, `git:`, `registry:`, `direct:`.

A direct link brings one file, so such a skill has no scripts and no resources.
That is the price of it.

A registry is a JSON file:

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

An entry that cannot be read is left out and the rest of the list still works.
The registries in `skills.registries` are offered on the page.

### The preview

The download waits in `~/.coderagent/cache/skills/` for half an hour. The page
shows:

- the source, the number of files and the digest of the content,
- the warnings — a skill with scripts is marked, because the model may run them,
- **the whole `SKILL.md`**, as it is. This is the only thing between you and a
  file that tells the model what to do, so read it.
- the list of the other files, with their sizes.

`Install` writes it to `~/.coderagent/skills/<name>/`; `Cancel` throws it away.

### What is checked

| Limit | Default | The key |
|---|---|---|
| The bytes of one download | 8 MiB | `skills.max_bytes` |
| The bytes of one file | 1 MiB | `skills.max_file_bytes` |
| The number of files | 2000 | `skills.max_files` |
| How deep the directories go | 16 | `skills.max_depth` |
| The seconds a download takes | 30 | `skills.timeout` |

The path of every file is checked too: a path that leaves the directory of the
skill, a link, a device file, a name Windows does not allow — all of them are
refused, and the download is thrown away instead of being half installed.

Only `https://` may be fetched, and a host that points inside the network is
refused as well, so the page cannot be used to reach the machines of your
network. A git address needs `git` on the machine; without it the page says so
instead of doing something else.

### The lock file

`~/.coderagent/skills.lock.json` says what was installed here and where it came
from:

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

Every file has its own sha256, and the skill has one digest over all of them.

**Check for an update** fetches the source again: the same digest means the same
content, a different one means the page shows the new one and asks before it
replaces the old. **Uninstall** removes a skill that came from the network. A
skill you put there yourself is yours — the page says so and leaves it alone.

### When it takes effect

**In a new session.** The index of the skills goes into the system prompt, and
that is built when the session starts, so a session that is running keeps the
skills it started with. `/skills` in the terminal reads the disk every time, so
it sees the new one right away.

### The configuration

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

| Key | What it does |
|---|---|
| `enabled` | `false` refuses the writes of the page. The skills that are on the disk are still read by the agent: the switch is about installing, not about using |
| `registries` | The `index.json` addresses the page offers |
| `github_token` | The token of GitHub, to get past the rate limit of the anonymous requests. It only goes into the headers of a request, and it is never written into the lock file — keep it out of the project file |
| `allow_insecure` | `true` lets `http://` be fetched. The rule is `https://` |
| `allowed_hosts` | The hosts that may point inside the network. The others may not |

The network switch of the session (`permissions.network`) is **not** used for
these downloads: it is about the commands the model runs, and a download is your
own action on the page.

### The scripts of a skill

A skill with scripts is marked in the preview. The model may run them with
`bash`, and that is the permission layer of the session as usual: installing a
skill does not give it more rights.

## A skill and a command

| | A skill | A command |
|---|---|---|
| Who calls it | The model, when the description fits | The user, with `/name` |
| What it is | Instructions the model follows | A message the user sends |
| What it leaves | Files, reports, commits | A message in the conversation |

A command is in `.coderagent/commands/*.md`, see
[The commands](coderagent_commands.md). A skill is in
`.coderagent/skills/<name>/SKILL.md`.

## The permissions

The `skill` tool is a tool that is asked for, like `bash`. Without a terminal
nobody can answer, so in a script the call is refused:

```bash
coder --task "..." --permission-mode bypass
```

or a rule of your own:

```yaml
# .coderagent/rules.yaml
rules:
  - tool: skill
    pattern: "*"
    decision: allow
```
