# The coding agent

`coder` is an interactive agent that works in a code repository. It reads the
code, writes the code, runs the commands and tells you what it changed. It
lives in the same package as `mini`, next to it:

```bash
pip install -e .            # the agent
pip install -e ".[mcp]"     # with the MCP servers
pip install -e ".[full]"    # with everything: swerex, modal, contree
```

The command is `coder`.

## The first session

```bash
cd my-project
coder
```

The interface opens in the directory of the project. Type what you want, for
example `fix the failing test in tests/test_parser.py`, and the agent works
through it. The status bar at the top shows the model, the size of the context,
what the session has cost so far, the sandbox and the permission mode.

Without a terminal there is one turn and then the answer:

```bash
coder --task "fix the failing test in tests/test_parser.py"
```

The keys of the model come from the environment or from the `.env` file of
mini-swe-agent (see [Global configuration](../advanced/global_configuration.md)).
The name of the model is `model.model_name` in the configuration, or
`MSWEA_MODEL_NAME` in the environment.

## The command line

| Option | What it does |
|---|---|
| `--task`, `-t` | The task. Without it, the interface opens when the terminal is interactive. |
| `--model`, `-m` | The model of this run |
| `--config`, `-c` | A configuration file, or `key=value` overrides |
| `--profile`, `-p` | A named piece of the configuration |
| `--cwd` | The directory of the session |
| `--permission-mode` | `default`, `acceptEdits`, `plan`, `bypass` or `readonly` |
| `--output-format` | `text` (the default) or `json` |
| `--output-schema` | A file with the JSON schema the answer has to fit |
| `--output-last-message` | Write the last answer of the agent to this file |
| `--resume <id>` | Continue the session with this id |
| `--continue` | Continue the last session of this directory |
| `--fork <id>` | Copy the session with this id and continue in the copy |
| `--list` | The sessions of this directory |
| `--tui` | Start the interface, even when there is no terminal |

`--print` is accepted and has no effect.

The overrides of `-c` are `key=value` pairs, the key is a path in the
configuration:

```bash
coder -c model.model_name=deepseek/deepseek-flash -c permissions.mode=plan
```

### The output

The text output is the conversation and one line about the turn:

```
[stop_reason=end_turn cost=0.0016 session_cost=0.0019 session=20261106-a1b2c3]
```

`cost` is what this turn cost, `session_cost` is what the whole session cost.
The json output has the same numbers in fields:

```bash
coder --task "..." --output-format json
```

```json
{
  "session_id": "20261106-a1b2c3",
  "messages": [{"role": "assistant", "content": "The test needed a fixture."}],
  "cost": 0.0016,
  "session_cost": 0.0019,
  "stop_reason": "end_turn",
  "error": "",
  "output": null
}
```

`stop_reason` is `end_turn`, `max_turns`, `cost_exceeded`, `token_limit`, `verify_failed`,
`schema_invalid`, `interrupted` or `error`. `error` is empty unless the turn failed.
`output` is the answer when a schema was asked for with `--output-schema`, and
`null` when it was not.

The answer itself goes into a file with `--output-last-message`:

```bash
coder --task "..." --output-last-message answer.md
```

The file holds the text of the last answer of the agent, nothing else.

### The trace of a session

```bash
coder export --session 20261106-a1b2c3 --format json --out trace.json
coder export --session 20261106-a1b2c3 --format otel --out trace.otlp
coder export --session 20261106-a1b2c3 --format otel --push
```

The trace is the event log of the session with the metrics of the session. With
`telemetry.otel_endpoint` in the configuration, the trace of every turn also
goes to that OpenTelemetry collector. See [Trace export](coderagent_export.md).

## The terminal interface

| Key | What it does |
|---|---|
| `ctrl+c` | Stop the turn that is running — and the tool that is running with it. A second time leaves. |
| `ctrl+q` | Leave. The session is settled in the memory first. |
| `ctrl+o` | Open the panel of the sessions. `enter` continues the one that is picked. |
| `↑` / `↓` | Walk through the messages you sent, the way a shell does. |
| `@` | Complete the path of a file under the working directory; `→` takes it. |

When the agent wants to run a tool that needs approval, the interface asks.
`y` allows it once, `n` refuses it, `a` always allows it: that answer writes a
rule into `~/.coderagent/rules.yaml`, so the same call — the same file, or the
same command — is allowed from then on, in every session. The refusal goes back
to the model, which then does something else.

The answers are listed one per line, each in a numbered box:

```
1 [*] y allow
2 [-] n deny
3 [-] a always allow
```

The box of the picked answer is starred in red, the others have a grey dash.
The arrow keys (`←`/`→` or `↑`/`↓`) move the pick, the numbers jump to an
answer, and `enter` confirms it.

The answer of the agent is rendered as Markdown: the code blocks, the tables
and the lists look the way they look in the README of a project. The text is
plain while it arrives, and rendered when it is complete.

When the turn is over the terminal shows a notification. A program of your own
may say it in the way you want it:

```yaml
ui:
  notify_command: notify-send
```

The program is called with the title and the body of the notification:
`notify-send coder "the work is done"`. A program that fails is a warning, not
a broken session. `ui.notifications: false` turns the notifications off. A
project may not choose the notifier either: that program runs on your machine,
with the answer of the agent in its hands.

A picture goes to the model with `/image`:

```bash
/image screenshot.png what is wrong with this layout?
```

A file goes to the model with its content in the message, with `/mention` or by
naming it in the question:

```bash
/mention src/app.py what does this do?
```

A file opens in your editor with `/open`:

```bash
/open src/app.py
```

The editor is the one you named in the configuration:

```yaml
ui:
  file_opener: vscode
```

`vscode`, `cursor` and `windsurf` are known by name; a command of your own works
too, with `{file}` where the file goes: `my-editor {file} --wait`. The file has to
be inside the working directory. A project may not choose the editor: that
program runs on your machine, so the choice is yours.

## The web interface

The same agent, in the browser:

```bash
pip install -e ".[web]"
coder web
```

The chat page is the terminal interface with a window around it, and the
settings page writes the model configuration — including the API key — for
you. The permissions are there too: the settings page writes the mode that the
new sessions get, the chat page switches the mode of the session that is
running. The pages, the API and the security model are in
[The web interface](coderagent_web.md).

## The configuration

Four layers, the later ones win:

1. the built-in defaults,
2. `.coderagent/config.yaml` of the project,
3. `~/.coderagent/config.yaml` of the user,
4. the `-c key=value` overrides of the command line.

A full example:

```yaml
model:
  model_name: deepseek/deepseek-flash
  api_key: sk-...
  api_base: https://api.deepseek.com
  model_kwargs:
    temperature: 0.0
  litellm_config: ~/.coderagent/litellm_config.yaml
  routing:
    cheap: deepseek/deepseek-flash
    summarize: deepseek/deepseek-flash

agent:
  max_turns: 50
  cost_limit: 5.0

tools:
  enabled: [read, write, edit, glob, grep, ls, bash, todo_write]
  disabled: [bash_output]
  bash_timeout: 120

permissions:
  mode: default
  deny_paths: ["*.env", "secrets/**"]
  include_dirs: ["../shared-library"]
  rules:
    - tool: bash
      pattern: "git push"
      decision: deny
      reason: pushing is not my job

context:
  context_window: 64000
  compact_threshold: 0.8
  summarize_model: deepseek/deepseek-flash

memory:
  enabled: true

sandbox:
  type: local
```

### The model

`model.model_name` is the model of the agent. `model.api_key` and `model.api_base`
are the key and the address of the provider; they have a field of their own, so
that a key is not one of the many parameters of the call. `model.model_kwargs`
goes to the provider as it is — except for `model`, `messages`, `tools`,
`stream` and `stream_options`: those belong to the call of the agent, and a
configuration that has one of them is refused at the start instead of breaking
the call at runtime. `model.routing` maps a purpose to a model:

| Purpose | What it is for |
|---|---|
| `main` | The agent itself |
| `cheap` | The small jobs: the sub agents that look around |
| `summarize` | The summary of a compacted context |
| `reflect` | What the session writes into the memory |
| `strong` | A stronger model, when the routing rules ask for it |
| `review` | The review of the changes (`/review`) |

`model.review_model` names the model of the `review` purpose when the routing
has no `review` of its own. Without it the review runs on the model of the
session. `model.routing` wins over `model.review_model`.

`model.routing_rules` are conditions on the state of the session:

```yaml
model:
  routing:
    strong: anthropic/claude-sonnet-4-5
  routing_rules:
    - when: "tokens > 50000"
      purpose: strong
```

The rules compare numbers only, they are parsed and not evaluated, so a
configuration file cannot run code. The interface says in the event stream when
the model changes and why. See [Model routing](coderagent_routing.md).

#### How much the model thinks

`model.reasoning_effort` says how long the model thinks: `minimal`, `low`,
`medium` or `high`. Empty is the default of the model, which is what most of
them are good at.

```bash
coder -c model.reasoning_effort=high --task "..."
```

The level is written in the words of the provider: OpenAI and the others want
`reasoning_effort`, Anthropic wants a number of tokens to think with
(`minimal` is 1024 tokens, `high` is 16384). A provider that does not know
the parameter refuses the call, and the refusal is not retried.

A level that does not exist is refused when the configuration is read, not in
the middle of a turn.

#### How much the model says

`model.verbosity` says how much the model says: `low`, `medium` or `high`.
Empty is the habit of the model, which is what most of them are good at.

```bash
coder -c model.verbosity=low --task "..."
```

`reasoning_effort` is how long the model thinks, `verbosity` is how much it
says. The two are independent: a model may think long and answer short.

The level is an instruction, not a parameter of the provider: it goes into the
system prompt of the session. Every provider understands it, and none of them
is asked for a parameter it may not know.

A level that does not exist is refused when the configuration is read.

#### Other providers

The model goes through [litellm](https://github.com/BerriAI/litellm), so every
model litellm knows works. The name carries the provider in front of it, and
the key of the provider comes from the environment:

| Model name | Provider | Environment variable |
|---|---|---|
| `anthropic/claude-sonnet-4-5` | Anthropic | `ANTHROPIC_API_KEY` |
| `openai/gpt-4o` | OpenAI | `OPENAI_API_KEY` |
| `deepseek/deepseek-flash` | DeepSeek | `DEEPSEEK_API_KEY` |
| `dashscope/qwen3-coder-plus` | Alibaba (DashScope) | `DASHSCOPE_API_KEY` |
| `moonshot/kimi-k2.5` | Moonshot | `MOONSHOT_API_KEY` |
| `minimax/minimax-m2` | MiniMax | `MINIMAX_API_KEY` (and `MINIMAX_API_BASE`) |
| `openrouter/qwen/qwen3-coder` | OpenRouter | `OPENROUTER_API_KEY` |

```bash
export DASHSCOPE_API_KEY=sk-...
coder -m dashscope/qwen3-coder-plus --task "..."
export MOONSHOT_API_KEY=sk-...
coder -m moonshot/kimi-k2.5 --task "..."
export MINIMAX_API_KEY=...
export MINIMAX_API_BASE=https://api.minimax.io/v1
coder -m minimax/minimax-m2 --task "..."
```

Three things to know:

- **`qwen/` is not a provider.** The Alibaba models live under `dashscope/`
  (or `qwen_ai_platform/`, the same thing under its old name). `qwen/` is the
  name of a model family, not of a route.
- **The window comes from the model name.** The context window is looked up by
  the part after the provider: `qwen` 32k, `deepseek` 64k, `kimi` 256k,
  `minimax` 200k, `claude` 200k, `gpt-` 128k, `gemini` 1M. When the model is
  new or the family is not in the table, set it yourself:
  `context.context_window: 262144`.
- **The model has to call tools.** The agent only works with a model that
  supports tool calling. The cheap models of a family usually do not, so keep
  them for `model.routing.cheap` only if they do.

The routing is what makes a mixed setup work: the main model does the work,
the cheap one does the looking around.

```yaml
model:
  model_name: dashscope/qwen3-coder-plus
  routing:
    cheap: moonshot/kimi-k2.5
    summarize: moonshot/kimi-k2.5
```

#### The aliases of a litellm config file

An endpoint that is not in the table above can have an alias. `model.litellm_config`
names a litellm config file, and the `model_list` of that file names the models:

```yaml
# ~/.coderagent/litellm_config.yaml
model_list:
  - model_name: nengpa/minimax-m2.7
    litellm_params:
      model: openai/MiniMax-M2.7
      api_base: https://api.nengpa.com/v1
      api_key: sk-cp-...
```

```yaml
# ~/.coderagent/config.yaml
model:
  model_name: nengpa/minimax-m2.7
  litellm_config: ~/.coderagent/litellm_config.yaml
```

The alias `nengpa/minimax-m2.7` is then a model like any other: `coder -m
nengpa/minimax-m2.7 --task "..."` works, and so does the routing.

A relative path is looked for in `~/.coderagent/` first and in the working
directory after it: the setting lives in a file that does not move, the working
directory does.

The `model` of an entry is the model litellm calls, with the provider in front of
it. The other parameters of the entry go to litellm as they are, so the key of a
third party endpoint stays in that one file instead of the configuration of the
agent. The settings of `model.model_kwargs` win over the ones of the alias, and
`model.api_key` and `model.api_base` win over both.

The `api_base` stops at `/v1`: litellm appends `/chat/completions` to it.

An alias only works when the model name is exactly one of the aliases of the file.
A name that is not in the `model_list` leaves the agent with none of the settings
of that file, and the agent says so instead of going on without them:

```
The model 'openai/MiniMax-M2.7' is not one of the aliases of ~/.coderagent/litellm_config.yaml (nengpa/minimax-m2.7): the settings of that file are not used.
```

### The tools

| Tool | What it does |
|---|---|
| `read` | Read a file. `offset` and `limit` cut a long file into pieces. |
| `write` | Write a file from scratch. |
| `edit` | Replace a piece of text in a file. |
| `multi_edit` | Several edits in one file, in order. |
| `apply_patch` | Apply a patch of blocks: change, add and delete files in one call. |
| `glob` | The files that match a pattern, e.g. `**/*.py`. |
| `grep` | Search for a regular expression. `glob` limits the files. |
| `ls` | List a directory. `depth: -1` lists everything below it. |
| `bash` | Run a command. `run_in_background` returns a task id at once. A local environment only. |
| `bash_output` | The output of a background command. |
| `bash_kill` | Stop a background command. |
| `todo_write` | The task list of the agent. Shown at the bottom of the interface. |
| `task` | Hand a job to a sub agent. |
| `skill` | Load the instructions of a skill. |

`tools.enabled` is the list of the tools the model may call, `tools.disabled`
takes some of them away. The tools of the MCP servers are always there.

Every tool result is cut to the budget of the context before the model sees it:
a command that prints a hundred thousand lines does not blow up the window. The
full result stays in the log of the session.

### The environment of the commands

The commands of the agent do not see everything you see. The key of the
provider is in the process of the agent, not in its shell:

```bash
echo [$OPENAI_API_KEY]   # [] — the agent does not see your key
```

The environment of the commands is yours by default (`shell_environment.inherit:
all`), except for the names that look like a secret. `*_API_KEY`, `*_KEY`,
`*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `*_PASSWD`, `*_CREDENTIALS` and
`*_ACCESS_KEY` are always left out.

| Option | What it does |
|---|---|
| `inherit` | `all` (everything but the secrets), `core` (only what a command needs), `none` (nothing) |
| `exclude` | Names that are left out, `*` works as a wildcard |
| `include` | Names that are kept, even when they look like a secret |
| `set` | Names that are set, no matter what |

```yaml
shell_environment:
  inherit: core
  exclude: ["MY_*"]
  include: ["MY_TOKEN"]
  set:
    CI: "1"
```

`core` keeps only `PATH`, `HOME`, the locale, the shell and the temporary
directories — what a command needs to run at all. `include` is the way to open
a secret again, one name at a time.

The project may hide more of the environment, never show what you hid: a
project that adds an `include` is ignored.

### The permissions

The mode decides what the agent may do without asking:

| Mode | What it does |
|---|---|
| `default` | Reading is free, writing and commands are asked for |
| `acceptEdits` | Writing is free, commands are asked for |
| `plan` | Nothing is changed. The agent only reads and answers. |
| `readonly` | Like `plan`, but the agent is told to describe the change instead of making it |
| `bypass` | Everything is allowed. For a container or a throwaway checkout. |

The mode can be changed while the session runs, with `/mode` or `/plan`.

`bypass` takes the guards off, so it asks once: `/mode bypass` says what it
would do and changes nothing, `/mode bypass --yes` switches it on.

The mode of the **project** may only take tools away: `plan` and `readonly` are
used, the other modes are ignored. The same goes for the rest of the
permissions — the project may not open directories outside the working
directory, its rules may only deny, and the tools it names may only remove
from the tools of the user. The permissions are the user's to decide.

`plan` and `readonly` make the permission layer deny the writing tools, so the
model is told about it: a `<permission_mode mode="...">` block goes into the
conversation, saying what it may do and what it should answer instead. The
block follows the mode, so it changes as soon as the mode changes.

The rules are more precise than a mode. A rule has a tool, a pattern and a
decision:

```yaml
permissions:
  rules:
    - tool: edit
      pattern: "tests/**"
      decision: allow
    - tool: bash
      pattern: "rm -rf"
      decision: deny
      reason: that command is not allowed
```

The pattern is a glob for the tools that touch a path (`read`, `write`,
`edit`, `multi_edit`, `glob`, `grep`, `ls`) and a regular expression for
`bash`, where it is matched against the beginning of each part of the command.
The decision is `allow`, `ask` or `deny`. Among the rules that match, the
strictest one wins: a `deny` is never undone by a later `allow`, and between
`allow` and `ask` the last one wins. A command is judged part by part and the
strictest part wins, so an allowed `pytest` does not carry a `rm` along with it.

`apply_patch` has no path of its own — it changes several files at once — so a
rule about it is about the whole call. Every file it touches is checked against
the bounds of the session anyway: a patch that reaches outside the working
directory is refused.

The rules of the project live in `.coderagent/rules.yaml`, the rules of the
user in `~/.coderagent/rules.yaml`. Both are read, in that order, so a rule of
the user beats a rule of the project with the same tool and pattern — except
that a `deny` is never beaten by anything. The rules of the project may only
**deny**: a project cannot allow itself something the user has to be asked for.

The rules that live in the configuration file (`permissions.rules`) are checked
when the configuration is read: a decision that is not `allow`, `ask` or `deny`,
or a key that does not exist, stops the session at the start instead of turning
into a rule that lets a call through. A rule of the project that is written
wrong is a deny: a broken deny must never become an allow.

```yaml
# .coderagent/rules.yaml
rules:
  - tool: bash
    pattern: "pytest"
    decision: allow
```

`permissions.deny_paths` are the paths that are off limits, whatever the mode
says. `permissions.include_dirs` are the directories outside the working
directory that the agent may still touch. Without them the agent stays inside
the directory of the session. The paths that the project denies are added to
the ones of the user, not put in their place.

The shell has its own boundaries: the commands that only look around (`ls`,
`cat`, `grep`, `git status`) go through without a question, the ones that
destroy something or send it out (`rm`, `curl`, `git push`) ask, and a path
outside the working directory is refused in every mode. The paths of a command
are the ones it names, variables and all, and a substitution runs a command
too: `cat $HOME/.ssh/id_rsa` is refused, and `echo $(rm -rf ~)` asks.

The network has a switch of its own: `permissions.network` is `allow` by
default, `deny` closes it.

```yaml
permissions:
  network: deny
```

When the network is closed, the commands that reach it are **refused** instead
of asked for: `curl`, `wget`, `pip install`, `git push` and the like. The
refusal holds in every mode, `bypass` included, and a rule of the user cannot
open the network again — the same way the boundaries of the disk hold. The
model is told about it: a `<permission_network policy="deny">` block goes into
the conversation, next to the one of the mode. The project may close the
network, never open it.

`/permissions` shows the mode and the rules that are in effect.

Without a terminal nobody can be asked, so a call that needs approval is
refused and the model is told that the user refused it. In a script, use
`--permission-mode bypass` for the calls that need it.

### The context

The context of the model has a window (`context.context_window`, by default
the window of the model). When the context comes close to the limit, the
older part of it is replaced by a summary. The summary is written by another
model (`context.summarize_model`), the older messages are not thrown away:
they are in the summary.

| Option | What it does |
|---|---|
| `context_window` | The size of the window. By default the one of the model. |
| `compact_threshold` | When to compact, as a share of the window. |
| `keep_recent_turns` | How many recent turns to keep when the window has room for them. |
| `keep_recent_token_ratio` | The share of the window to keep when the window has room for it. |
| `compact_every_turns` | Compact after that many turns, even when the window is free. |
| `reserved_output` | The room that is kept for the answer of the model. |
| `auto_compact` | Whether the agent compacts on its own. |
| `project_doc_max_bytes` | The bytes one instruction file may take. A longer file is cut short. |

`/compact` compacts now.

The schemas of the tools go with every request, so they count against the
window: a session with many tools compacts a little sooner.

`/recap` summarizes the conversation without changing it: nothing is dropped and
nothing is compressed, the summary does not go into the context of the model. It
is a report for you, not a step of the work.

`/side <question>` asks a question in a conversation that goes aside: it has its
own session and its own log, and the conversation you are in is not touched. The
question and the answer are recorded in your session, so the agent does not lose
the thread of the work.

```bash
/recap
/side what does the retry logic of the client do?
```

### The memory

At the end of a session the agent asks the model what is worth remembering.
The facts about the project are written right away, the preferences of the
user wait for a confirmation.

```bash
/memory                # the memory of the project and of the user
/memory confirm        # write the pending preferences
/memory forget <text>  # remove a fact
```

The project memory is `.coderagent/memory/projects.md`, the preferences of the
user are `~/.coderagent/CLAUDE.md`. `memory.enabled: false` turns the whole
thing off, the model is not even asked. See [Memory](coderagent_memory.md).

### The checkpoints

Before a file is written, the agent takes a checkpoint of it. The checkpoints
are kept per session, the last 50 of them (`checkpoint.keep`). `/rewind` lists
them, and with an id it puts the files back and rolls the conversation back to
that point:

```bash
/rewind                 # the checkpoints of the session
/rewind 20261106-a1b2c3  # put the files of that checkpoint back
```

`checkpoint.enabled: false` turns them off.

### The sandbox

The commands of the agent run in a sandbox. By default it is the machine of
the user:

```yaml
sandbox:
  type: local
```

`swerex_docker`, `swerex_modal`, `bubblewrap` and `contree` are the other
ones. The options of the sandbox go to the environment as they are; the ones
the environment does not know are ignored:

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
  cwd: /workspace
```

The sandbox has no policy of its own: the network policy belongs to the
environment, the paths belong to the permission layer.

The local sandbox has three modes. The operating system enforces them —
Seatbelt on macOS, bubblewrap on Linux:

```yaml
sandbox:
  type: local
  mode: workspace-write
```

`full-access` is the default, `workspace-write` writes only inside the working
directory, `read-only` writes nothing. The mode and the permission mode are two
axes: the permissions ask the user, the sandbox asks nobody. See
[Sandbox](coderagent_sandbox.md).

A project may close the sandbox but never open it, and it may not choose where
the commands run: the `type` of the sandbox and the options of the environment
are the decision of the user.

## What the agent reads

The agent reads the instructions of the project before it starts. The files are
`AGENTS.md` and `CLAUDE.md`, in this order:

```bash
coder --task "/init"   # write an AGENTS.md for this project
```

`/init` writes a template with the layout of the directory; the model is not
asked. It does nothing when the file already exists.

The user file `~/.coderagent/CLAUDE.md` comes first, then the repository, then
the project. An `AGENTS.md` in a subdirectory is read when the agent touches
something in it.

The rules of the repository are read even when the agent starts in a
subdirectory of it, and they come before the rules of the directory.

One instruction file may take 32768 bytes (`context.project_doc_max_bytes`).
A longer file is cut short, and the agent is told that it did not see all of
it — a huge `AGENTS.md` does not eat the whole window. The memory files are
cut the same way.

## What the agent can delegate

### The sub agents

A sub agent works in its own context and returns a conclusion, so the main
context stays clean. The agent calls the `task` tool when a job is too big for
the main context: searching the whole code base, changing the same pattern
everywhere, checking a result on its own.

Three of them are always there:

| Name | What it does | Tools |
|---|---|---|
| `code-explorer` | Find code, follow a call chain | `read`, `grep`, `glob`, `ls` |
| `verifier` | Run the tests, reproduce the bug | `read`, `grep`, `glob`, `bash` |
| `refactorer` | Change the same pattern everywhere | `read`, `edit`, `grep`, `glob` |

Your own sub agents are markdown files in `.coderagent/agents`:

```markdown
---
name: doc-writer
description: Write the documentation of a module.
tools: [read, grep, glob]
model_purpose: cheap
max_turns: 15
---
You write the documentation of a module. Read the code, then write the docs.
```

The tools are a white list: the sub agent cannot reach anything else. The
files of the user are in `~/.coderagent/agents`. See
[Sub agents](coderagent_subagents.md).

### The skills

A skill is a package of instructions, scripts and resources:

```
.coderagent/skills/pdf-report/
├── SKILL.md
├── scripts/
│   └── make_report.py
└── assets/
    └── template.docx
```

```markdown
---
name: pdf-report
description: Make a PDF report out of a folder of notes.
---
Run `scripts/make_report.py` to build the report...
```

The model sees the name and the description of every skill, and loads the
whole one when the description fits the task. The files of the user are in
`~/.coderagent/skills`. See [Skills](coderagent_skills.md).

### The plugins

A plugin adds tools, commands or hooks to the agent. It is a directory
with a `plugin.py` in it, and it runs in the process of the agent, without a
sandbox. A plugin is only loaded when it is trusted:

```bash
/plugins            # the plugins that were found
/plugins trust hello
```

See [Plugins](coderagent_plugins.md).

### The hooks

A hook is a command of yours that runs at an important moment of the session:
before a tool runs, after it ran, when the session starts or ends. A hook can
block an action, rewrite its arguments or add something to the context.

```yaml
hooks:
  events:
    PreToolUse:
      - matcher: "bash"
        hooks:
          - type: command
            command: ./scripts/guard.sh
```

See [Hooks](coderagent_hooks.md).

### The MCP servers

The tools of an [MCP](https://modelcontextprotocol.io) server are available
under the name `mcp__<server>__<tool>`. The MCP SDK is optional:

```bash
pip install "mini-swe-agent[mcp]"
```

```yaml
mcp:
  servers:
    - name: filesystem
      command: npx -y @modelcontextprotocol/server-filesystem .
```

See [MCP servers](coderagent_mcp.md).

### The code of a project

Some of the configuration of a project runs a program without asking anything:
an MCP server, a hook, a verify command. That program was not written by the
user, so cloning a repository must not be enough to run it.

The code of the **project** therefore waits for a decision. The code of the
**user** — in `~/.coderagent/config.yaml` — is the user's own, and is used as
it is:

```bash
/trust            # the code that waits for a decision
/trust 1          # trust the first one of the list
```

The decision is remembered in `~/.coderagent/trusted.json`, and it belongs to
the **command** it was made for: a server or a hook whose command changes is a
thing that has to be trusted again. What is left out is left out entirely, so
a project that is not trusted does not take the servers of the user away.

What waits is only the code. The rest of the configuration of the project —
the instructions — is used as it is, because it says what the agent may do, not
what it may run. The permissions are the exception: the project may only take
tools away, never give them. The model is the other exception: where the
conversation goes is the decision of the user, so the whole `model` section of
a project is dropped. So are the two other places where a model is named:
`context.summarize_model` of a project, and the `model` of a command of the
project. The commands of the user, in `~/.coderagent/commands`, may name one.

The same holds for the programs a project would run on your machine: the
editor of `ui.file_opener`, the notifier of `ui.notify_command` and the
environment of `sandbox.type` are dropped from the configuration of a project.
A project may close the sandbox, never open it, and it may never say where its
commands run.

## The sessions and the money

A session is an append-only log of events, and that log is the source of
truth. The sessions live in `~/.coderagent/sessions`: one `.jsonl` file with the
events of a session and one `.meta.json` file with its metadata.

```bash
coder --list              # the sessions of this directory
coder --resume <id>       # continue one of them
coder --fork <id>         # continue a copy of one of them
```

Inside the interface, `/clear` starts a new session, `/resume` and `/fork` do
the same as on the command line.

A session has a life of its own:

| Command | What it does |
|---|---|
| `/rename <name>` | Give the session a name |
| `/archive [session-id]` | Put a session away, or take it out again |
| `/delete <session-id>` | Remove a session and everything in it |

A session that is put away is not in the list of `/resume`, but it is still there
and `/resume <id>` opens it. The session you are in cannot be deleted: start a
new one (`/clear`) first. The name of a session is in `/status` and in the list
of `coder --list`.

The history of the sessions grows with every session. Two settings say how much
of it is kept:

```yaml
history:
  persistence: save-all   # or save-none: nothing is written to the disk
  max_bytes: 0            # the bytes the history may take, 0 is no limit
```

With a limit, the oldest sessions are deleted when the history grows over it.
The session that is running is never one of them. A project may not touch these
settings: the history belongs to you.

A session that was killed in the middle of a tool call can still be continued:
the call whose result never came back is given a result that says so, so the
history the model sees stays whole. The same happens after a `/rewind` that
drops the result of a call.

`/cost` shows what the session has cost and where the money went:

```
model: deepseek/deepseek-flash
calls: 9
tokens in the context: 120433
tokens spent: 45678
cost so far: $0.4200
cost: $0.4200
tokens: 120433 in, 4567 out
model calls: 9
tool calls: 14
duration: 42.1s
by purpose:
  main        $0.3800
  cheap       $0.0400
by model:
  deepseek/deepseek-flash  $0.4200
by tool:
  read        8
```

The bill belongs to the session: a new session starts at zero, whatever the
session before it spent. The same number is in the trace, in `/status` and in
the `session_cost` of the command line.

## The files

| Path | What it is |
|---|---|
| `.coderagent/config.yaml` | The configuration of the project |
| `.coderagent/rules.yaml` | The permission rules of the project |
| `.coderagent/agents/*.md` | The sub agents of the project |
| `.coderagent/skills/*/SKILL.md` | The skills of the project |
| `.coderagent/plugins/*/plugin.py` | The plugins of the project |
| `.coderagent/commands/*.md` | The commands of the project |
| `.coderagent/memory/projects.md` | What the agent remembers about the project |
| `.coderagent/pending-memory.md` | The preferences that wait for a confirmation |
| `AGENTS.md`, `CLAUDE.md` | The instructions of the project |
| `~/.coderagent/config.yaml` | The configuration of the user |
| `~/.coderagent/litellm_config.yaml` | The aliases of the models |
| `~/.coderagent/rules.yaml` | The permission rules of the user |
| `~/.coderagent/CLAUDE.md` | The instructions and the preferences of the user |
| `~/.coderagent/agents/`, `~/.coderagent/skills/`, `~/.coderagent/plugins/` | The extensions of the user |
| `~/.coderagent/commands/` | The commands of the user |
| `~/.coderagent/trusted-plugins.json` | The plugins the user trusts |
| `~/.coderagent/sessions/` | The event log of the sessions |
| `~/.coderagent/checkpoints/` | The checkpoints of the sessions |

`MSWEA_CODER_HOME` moves the whole user directory somewhere else.
