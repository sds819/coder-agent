# The features of the coding agent

A list of everything `coder` can do, one line per feature, with an example and
the errors of every part. The pages that describe a part in detail are linked at
the end of each section.

> 中文版：[coding agent 的功能](coderagent_features_zh.md)

## The ways to run it

- **One turn from the terminal** — `coder -t "fix the failing test"`. The
  answer is printed as text, or as JSON with `--output-format json`.
- **One turn with a shape** — `coder -t "..." --output-schema answer.json`. The
  answer is JSON that fits the schema, and the JSON of the turn has it in
  `output`.
- **One turn into a file** — `coder -t "..." --output-last-message answer.md`.
  The file holds the last answer of the agent, nothing else.
- **The terminal interface** — `coder` without a task, or `coder --tui`. A
  full screen interface with a status bar, tool cards and approvals.
- **The browser** — `coder web`. The same agent in a chat page, with a
  settings page for the model.
- **As an API** — every action of the browser is a plain HTTP call, so a
  script can drive the agent.
- **As a library** — `coderagent.run.run_turn` and `build_loop` put the agent
  into another Python program.
- **In a benchmark** — the run scripts of mini-swe-agent solve SWE-bench and
  ProgramBench with the same model interface.

### Example

```bash
# One turn, the answer as text.
coder -t "add a docstring to src/app.py"

# One turn, the answer as JSON (for a script).
coder -t "list the files of this directory" --output-format json

# One turn, the answer as JSON that fits a schema.
coder -t "list the files of this directory" --output-schema files.json

# One turn, the answer in a file.
coder -t "list the files of this directory" --output-last-message answer.md

# The terminal interface.
coder                      # with a terminal this is the TUI
coder --tui                # the same, said explicitly

# The browser.
coder web --cwd . --port 8765

# A session of this directory, the newest first.
coder --list
```

The JSON of one turn has the fields `session_id`, `messages`, `cost`,
`session_cost`, `stop_reason`, `error` and `output`:

```json
{
  "session_id": "20261109-3f0a91",
  "messages": [{"role": "assistant", "content": "I added the docstring."}],
  "cost": 0.0012,
  "session_cost": 0.0143,
  "stop_reason": "end_turn",
  "error": "",
  "output": null
}
```

`cost` is what the turn cost, `session_cost` what the whole session has cost
so far. `output` is the answer when a schema was asked for, and `null` when it
was not.

`stop_reason` is one of `end_turn`, `max_turns`, `cost_exceeded`, `token_limit`, `verify_failed`,
`schema_invalid`, `error` and `interrupted`.

### The shape of the answer

`--output-schema` takes a file with a JSON schema. The answer of the agent has
to fit it, and the schema is checked here, in the agent, not by the provider:

```json
{
  "type": "object",
  "properties": {"files": {"type": "array", "items": {"type": "string"}}},
  "required": ["files"],
  "additionalProperties": false
}
```

The keywords that are understood are `type` (a name or a list of names),
`properties`, `required`, `additionalProperties`, `items`, `enum` and
`nullable`. A schema that uses anything else is not checked, not refused: the
answer is simply not validated against that part.

The model is told the schema before it starts, and an answer that does not fit
is **given back to it** with the errors, so that it can try again. It gets two
answers; when the second one does not fit either, the turn stops with
`stop_reason` `schema_invalid` and the errors are in `error`.

#### What is checked, and what is not

The check is done by a small validator of the agent, not by the provider. The
model is only **asked** for JSON that fits the schema — the schema is in the
system prompt — and the answer is checked afterwards. The provider never sees
the schema, so a model that ignores the request costs one retry.

The validator knows these keywords and nothing else:

| Keyword | What it does |
|---|---|
| `type` | One name or a list of names: `string`, `integer`, `number`, `boolean`, `object`, `array`, `null` |
| `properties` | The type of a field, checked in place |
| `required` | The field has to be there |
| `additionalProperties: false` | A field that is not in the schema is an error |
| `items` | The elements of an array, checked one by one |
| `enum` | The value has to be one of the list |
| `nullable` | `null` is allowed |

Every other keyword (`anyOf`, `$ref`, `pattern`, `minimum`, …) is **ignored**:
the part of the schema that uses it is not checked, and the answer is not
refused either. A schema that relies on them looks strict and is not.

Two things the validator is strict about:

- a boolean is not a number — `{"count": true}` does not fit
  `{"count": {"type": "integer"}}`;
- `nullable` only adds `null` to the values that are allowed, it does not
  loosen the type — `{"type": "integer", "nullable": true}` still refuses `""`.

The errors say where the answer is wrong, so the model knows what to fix:
`'files[1]' must be string`, `the answer is missing 'files'`, `the answer has
the unknown field 'extra'`.

#### Reading the answer out of the text

The answer of the model is text, and the JSON is taken out of it:

1. the whole text is JSON — it is used as it is;
2. the text is wrapped in a code fence — the fence is taken off;
3. there is a sentence in front of the JSON — the part between the first `{`
   and the last `}` is used.

A top-level **array** is read when it is the whole answer. An array with a
sentence around it is not read as an array: the third rule looks for braces,
so it takes the part between the first `{` and the last `}` — the object
*inside* the array. The check then says the answer is not an array, and the
model is asked again.

#### The two answers

The model gets two answers. The first one that does not fit is **given back**
to it, with the errors, as a new message — the agent is called back, not
blocked. When the second one does not fit either, the turn ends with
`stop_reason` `schema_invalid`, the errors are in `error` and `output` stays
`null`.

The shape is the last of the three gates: the `Stop` hook and the verification
commands come first, so a turn that one of them sends back never reaches the
check. The shape belongs to the loop, not to one conversation: switching
sessions keeps it.

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `no task given` | No `-t`, no `--tui`, and stdin is not a terminal (a script, a pipe). | Give a task: `coder -t "..."`. |
| `session 20261109-3f0a91` | The same as above, but a session was found to continue. | Same; add `-t` to run a turn in it. |
| `Unknown command '/foo'. Try /help.` | The line started with `/` but no command has that name. | Check the spelling, or `/help` for the list. |
| `ValueError: 'bogus' is not a valid PermissionMode` | `--permission-mode bogus` — the flag is checked when the policy is built, and the exception is not caught. | Use one of `default`, `acceptEdits`, `plan`, `readonly`, `bypass`. |
| `ValueError: Unknown output format: xml` | `--output-format` accepts only `text` and `json`. | Use `text` or `json`. |
| `Invalid value: the schema file is not valid JSON: ...` | The file of `--output-schema` does not hold JSON. | Fix the file, or drop the flag. |
| `Invalid value: the schema file cannot be read: ...` | The file of `--output-schema` is not there. | Check the path. |
| `stop_reason` is `schema_invalid` | The model did not answer with JSON that fits the schema, twice. | The errors are in `error`; the messages of the turn say what the model was told. |
| The answer passes the check but is not what you expected | The schema uses a keyword the validator does not know (`anyOf`, `$ref`, …), so that part was not checked at all. | Write the schema with the keywords above, and read the answer in `output`. |
| `Unknown format 'xml'. Use json or otel.` | `coder export --format` accepts only `json` and `otel`. | Use `json` or `otel`. |
| `no sessions yet` | `--list` found no session in this directory. | Nothing to do; run a turn first. |
| `coder web: cannot listen on 127.0.0.1:8765 (Address already in use).` on stderr, exit code 1 | The port is taken. The server checks this itself before it starts, because uvicorn's own error does not say what to do. | Use another port: `coder web --port 8766`. |

`coder` exits with `0` after a normal turn, whatever the answer was, and with
`1` when it could not start at all (a bad flag value, a port that is taken).

## The models

- **Any provider litellm knows** — OpenAI, DeepSeek, Anthropic, Gemini,
  Mistral, OpenRouter, … The provider in front of the name says who is
  called: `deepseek/deepseek-flash`.
- **Third party endpoints** — an OpenAI compatible address in `api_base`, with
  its own key. The address may be pasted with the `/chat/completions` at the
  end; the part behind `/v1` is cut off, because litellm adds it itself.
- **Aliases** — a litellm config file with a model list. The model name can
  then be an alias of that list, and the key of the endpoint stays in the file.
- **Cache control** — `set_cache_control: default_end` for the providers that
  support it. Any other value is refused.
- **How much the model thinks** — `reasoning_effort`: `minimal`, `low`,
  `medium` or `high`. Empty is the default of the model. The level is written
  in the words of the provider: `reasoning_effort` for OpenAI and the others,
  a number of tokens for Anthropic.
- **How much the model says** — `verbosity`: `low`, `medium` or `high`. Empty is
  the habit of the model. The level is an instruction in the system prompt, so
  every provider understands it.
- **A separate model for the review** — `model.review_model`. `/review` runs on
  that model when the routing has no `review` of its own.
- **Retries** — `max_retries`, three by default, the same in the terminal and in
  the browser.
- **Routing by purpose** — a different model for `main`, `cheap`, `summarize`,
  `reflect`, `strong` and `review`.
- **Routing by the state of the session** — a rule like `tokens > 50000`
  switches to another model, and the reason is in the event log.
- **A separate model for the summary** — `context.summarize_model`, empty
  means the model of the agent.
- **Streaming** — the answer arrives piece by piece, in the terminal and in
  the browser.

### Example

```bash
# The provider is the part in front of the slash.
coder -t "..." -m deepseek/deepseek-flash

# A third party endpoint that speaks the OpenAI protocol.
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

The model of a turn is decided in this order:

1. the model the user picked with `/model` (it wins over everything),
2. the first `routing_rules` entry whose condition holds,
3. the automatic policy: the budget is nearly used up → `cheap`, the context is
   big (> 50000 tokens) or the session is long (> 30 turns) → `strong`,
4. `routing.main`, and without it the model of the agent.

When the model changes, the event log says why:

```
Switched from deepseek/deepseek-flash to deepseek/deepseek-chat: the context has grown
```

The reasons are `the budget is nearly used up`, `the context has grown`,
`the session has many turns`, `the rule '<when>' holds` and
`the rules of the routing say so`.

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `LLM Provider NOT provided` | The model name has no provider in front of it. | Write `openai/<name>` for an OpenAI compatible endpoint, or `deepseek/<name>`. |
| `ValueError: Invalid mode: {mode}` | `set_cache_control` is neither `default_end` nor empty. | Use `default_end`, or remove the line. |
| `unknown reasoning effort '{level}'` | `reasoning_effort` is not one of `minimal`, `low`, `medium`, `high`. | Use one of those four, or remove the line for the default of the model. |
| `unknown verbosity '{level}'` | `verbosity` is not one of `low`, `medium`, `high`. | Use one of those three, or remove the line for the habit of the model. |
| `'model_kwargs' must not have '{key}'` | `model_kwargs` has a parameter of the call: `model`, `messages`, `tools`, `stream` or `stream_options`. | Remove it: the agent sets those itself. |
| `the file does not exist` | `model.litellm_config` points at a file that is not there. | Fix the path; a relative one is looked for in `~/.coderagent/` and in the working directory. |
| `the file is not valid YAML: {error}` | The alias file cannot be parsed. | Fix the YAML. |
| `the file has no model_list` | The alias file has no `model_list`. | Add the list of the models with their `litellm_params`. |
| `'{name}' is not one of the aliases of this file` | The model name is not in the `model_list` of the alias file. | Use one of the aliases, or drop `litellm_config`. |
| `The model '{name}' is not one of the aliases of {file}` | The model name is not in the `model_list` of the alias file, so not one setting of that file is used. | Use one of the aliases, or drop `litellm_config`. |
| `BadRequestError` | The provider refused the request (a wrong key, a wrong name, a wrong parameter). | It is **not** retried; the message of the provider is the answer. |
| `AuthenticationError` | The key is missing or wrong. | Set `model.api_key`, or the key of the endpoint in the alias file, or the key of the provider in the environment (`OPENAI_API_KEY` for `openai/…`). |
| `ContextWindowExceededError` | The request was larger than the window of the model. | Lower `context.context_window`, or use a model with a bigger window. |

Retries are a separate thing from the errors above: a rate limit or a timeout
is retried, a bad request is not. The number of attempts comes from
`model.max_retries` (3 by default) in every interface — the terminal and the
browser alike. The environment variable `MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT`
overrides it, which is handy when a test should not wait.

## The configuration

The configuration is read in four layers, the later ones win: the built-in
defaults, `.coderagent/config.yaml` of the project, `~/.coderagent/config.yaml`
of the user, and the `-c key=value` overrides of the command line.

A setting that means nothing is **refused**, not taken silently:

| What you see | What it means | What to do |
|---|---|---|
| `unknown permission mode '{name}'` | `permissions.mode` is not one of the five modes. | Use `default`, `acceptEdits`, `plan`, `bypass` or `readonly`. |
| `unknown network policy '{name}'` | `permissions.network` is not `allow` or `deny`. | Use one of the two. |
| `unknown tool '{name}'` | `tools.enabled` or `tools.disabled` names a tool that does not exist. | Use the name of one of the built-in tools. |
| `unknown hook event '{name}'` | `hooks.events` names a moment that is not one of the moments of a session. | Use one of the events of the [hooks](coderagent_hooks.md). |
| `unknown purpose '{name}'` | `model.routing` or a routing rule names a job that does not exist. | Use one of the [purposes](coderagent_routing.md). |
| `'{name}' is not a condition` | A routing rule is not a key, an operator and a number. | Write it as `tokens > 50000`. |
| `Extra inputs are not permitted` | A section or a key is written wrong (`permissons`). | Fix the name of the section. |
| `Input should be greater than or equal to 0` | A number is negative. | Use a number of zero or more. |

The **project** is treated differently from the user: a repository may not break
the session, so what it writes wrong is left out, key by key, and the rest of
its file is kept. The projects may also lower the ceilings of a session, never
raise them.

## The tools

The fourteen built-in tools:

| Tool | What it does |
|---|---|
| `read` | Read a file, with the line numbers |
| `write` | Write a file, creating it if needed |
| `edit` | Replace one exact string in a file |
| `multi_edit` | Several edits in one file — all of them, or none |
| `apply_patch` | Apply a patch of blocks: change, add and delete files in one call |
| `glob` | Find files by pattern (`*` in one segment, `**` across directories) |
| `grep` | Search the contents with a regular expression, by lines, by file or by count |
| `ls` | List a directory; `depth: -1` walks the whole tree |
| `bash` | Run a shell command, with a timeout or in the background |
| `bash_output` | The output of a background command so far |
| `bash_kill` | Kill a background command |
| `todo_write` | The task list of the current work |
| `task` | Hand a self contained job to a sub agent |
| `skill` | Load the instructions of a skill |

- **Tools of MCP servers** — `mcp__<server>__<tool>`, from every server that
  is configured.
- **The tools of an MCP server can be picked** — `enabled_tools` (only these)
  and `disabled_tools` (not these) choose the tools of one server by name, and
  `*` means all of them. A tool that is not shown is not in the list of tools
  at all, so the model does not see it.
- **Tools of plugins** — a plugin can add tools, commands and hooks.
- **The schemas are trimmed to the budget** — the schemas of the tools may
  take a tenth of the context window; `tools.schema_budget_tokens` sets
  another budget. When they do not fit, the ones that matter least go first.
  `bash` and `read` are never dropped.
- **The tool set is configurable** — `tools.enabled` is the list of the tools
  the model may call, `tools.disabled` takes single ones away.
- **Every result is cut to the budget** — `tools.max_output_tokens` (8000 by
  default) is the size of one tool result. A long one keeps its head and its
  tail, and says in the middle what was left out. The full result stays in the
  log of the session.
- **The commands do not see your keys** — the environment of the commands is
  yours, but the names that look like a secret (`*_API_KEY`, `*_TOKEN`, …) are
  left out. `shell_environment` says how much of it the agent sees.

### Example

```bash
# The model calls these, but you can call them yourself to try them out.
```

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

`multi_edit` takes a list and is all or nothing:

```json
{"tool": "multi_edit", "params": {"path": "src/app.py", "edits": [
  {"old_string": "import os", "new_string": "import os\nimport sys"},
  {"old_string": "def main():", "new_string": "def main(argv=None):"}
]}}
```

`apply_patch` takes a patch with context, the way Codex writes one. It changes
several files in one call, and it is **all or nothing**: when a hunk does not
fit, no file is changed.

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

A line that starts with a space stays, a line with `-` goes, a line with `+`
comes. The text after `@@` is a hint about where the hunk belongs; the block
itself is what has to match. The patch may also delete a file, and it ends
with `*** End Patch`.

`grep` has three modes: `content` (the default), `files_with_matches` and
`count`. It returns at most 100 matches, `glob` at most 200 files.

A link that leads out of the working directory is not followed: `grep` skips
it, so a link to `~/.ssh/id_rsa` is not read. `ls` shows the link itself, not
the file it points at.

### When something goes wrong

Every tool answers with an `Error: ...` line instead of raising, so the model
sees the message and can correct itself. The messages are:

| Tool | Message |
|---|---|
| `read` | `Error: file not found: {path}. Use \`ls\` to see what is in that directory.` |
| `read` | `Error: '{name}' is a directory. Use \`ls\` to list it.` |
| `read` | `Error: '{name}' is a binary file.` |
| `edit` | `Error: old_string not found in {path}. Use \`read\` to see the exact content, then retry with more context.` |
| `edit` | `Error: old_string is not unique in {path}: it appears {count} times (lines {...}). Include more surrounding context to make it unique, or set replace_all=true.` |
| `multi_edit` | `Error: Edit #1 failed, no changes were written. {inner}` — the file is untouched. |
| `apply_patch` | `Error: the patch must start with '*** Begin Patch'` / `Error: the patch must end with '*** End Patch'` — the patch is not a patch. |
| `apply_patch` | `Error: the context of the hunk does not match {path}: '{line}' is not where the patch says it is. Read the file again and use the lines that are really there.` |
| `apply_patch` | `Error: the file {path} exists already.` — a file to add is there. |
| `apply_patch` | `Error: file not found: {path}.` — the file to change or to delete is not there. |
| `apply_patch` | `Error: '{path}' is outside the working directory {cwd}.` — the patch leaves the directory of the session. |
| `grep` | `Error: invalid regular expression '{pattern}': {error}` |
| `grep` | `Error: \`output_mode\` must be one of content, files_with_matches, count (got '{mode}').` |
| `glob`/`grep`/`ls` | `Error: path not found: {path}.` / `Error: not a directory: {path}.` |
| `bash` | `Error: \`command\` is required and must be a non-empty string.` |
| `bash_output` | `Error: unknown task id '{id}'.` |
| `todo_write` | `Error: todo #1 has invalid status '{status}'. Use one of pending, in_progress, completed.` |
| `task` | `Error: unknown sub agent '{name}'. Available sub agents: {...}.` |
| `skill` | `Error: unknown skill '{name}'. Available skills: {...}.` |

The errors of the executor itself are raised inside the result of the call:

| Message | Meaning |
|---|---|
| `Error: unknown tool '{name}'. Available tools: {...}.` | The model called a tool that is not registered — usually because `tools.enabled` was narrowed. |
| `Error: permission denied for '{tool}'. {reason}` | A rule or a mode refused the call. |
| `Error: the user denied '{tool}'.` | Somebody pressed `n` at the approval. |
| `Error: '{tool}' needs approval but no approver is available. Run with --permission-mode bypass to allow it.` | A call that needed approval in a headless run. `--permission-mode bypass` or a rule that allows it. |
| `Error: the hook blocked '{tool}'. {reason}` | A `PreToolUse` hook refused the call. |
| `Error: '{tool}' failed: {type}: {e}` | The tool itself raised. |

A `bash` call that ends with a non-zero exit code is **not** an error: the exit
code is part of the output, as `[exit code 1]`. A command that runs longer than
`tools.bash_timeout` (120 seconds by default) fails with:

```
An error occurred while executing the command: Command 'sleep 60' timed out after 120 seconds
```

A background command answers with `Started background task {id}: {cmd}` and is
read with `bash_output`, killed with `bash_kill`. It runs in the environment of
the session, with the environment of the session. Only a local environment can
start one: in a container the call is refused, because the command would run on
the machine of the user, outside of the boundary of the session. A background
task belongs to the session: it is stopped when the process of the session
ends, and its log is removed with it.

The output of a tool is written to the log of the session and sent to the
provider. What looks like a secret in it — an API key, a token, a password, a
private key — is replaced with `[redacted]` before either happens. The log
holds the output as the model saw it, cut to the budget of the context, so a
tool that prints a hundred megabytes does not fill the log of the session. A
file that holds a secret is stored in a checkpoint without it, and it is not
restored by `/rewind`: the file is left as it is and the command says which one
it was.

## The permissions

- **Five modes** — `default`, `acceptEdits`, `plan`, `readonly` and `bypass`.
- **`bypass` asks once** — it takes the guards off, so `/mode bypass` says what
  it would do and changes nothing; `/mode bypass --yes` switches it on.
- **The model is told** — in `plan` and `readonly` the agent knows that it may
  not change anything, and answers with what it found instead.
- **The shell has boundaries** — the commands that only look around go through,
  the ones that destroy something or send it out ask, and a path outside the
  working directory is refused.
- **Rules** — `~/.coderagent/rules.yaml` and `.coderagent/rules.yaml` decide
  per tool and per pattern. The user level file wins, except that a `deny` is
  never beaten. The rules of the project may only deny. The rules of the
  configuration file are checked when the configuration is read: a wrong
  decision or a wrong key stops the session at the start, and a rule of the
  project that was written wrong is a deny.
- **`Always allow`** — the button of an approval writes a rule, so the same
  call — the same file, or the same command — goes through from then on.
- **Denied paths** — `permissions.deny_paths`, paths the agent may not touch.
- **Extra directories** — `permissions.include_dirs`, directories outside the
  working directory the agent may still touch.
- **A switch for the network** — `permissions.network` is `allow` by default
  (the commands that reach the network ask) and `deny` **refuses** them. The
  refusal holds in **every** mode, `bypass` included, and a rule of the user
  cannot widen it. The project may close the network, never open it.
- **Three answers** — allow, deny, always allow. Nobody answers, the call is
  denied: in the browser after `ui.approval_timeout` seconds (five minutes by
  default), in the terminal after no limit at all, because somebody is there.
- **In the terminal** the answer is picked with the arrow keys, in the browser
  with the buttons of the card. Without a terminal the answer is a denial.
- **Hooks run before the permission check** — a hook may rewrite the call or
  block it, and then the permission check sees the rewritten call.

### Example

The mode decides what happens without any rule:

| Mode | `read`, `glob`, `grep`, `ls` | `write`, `edit`, `multi_edit` | `bash` | `todo_write`, `bash_output`, `bash_kill` |
|---|---|---|---|---|
| `default` | allow | ask | ask¹ | allow |
| `acceptEdits` | allow | allow | ask¹ | allow |
| `plan` | allow | deny | deny | allow |
| `readonly` | allow | deny | deny | allow |
| `bypass` | allow | allow | allow | allow |

¹ The commands that only look around — `ls`, `cat`, `grep`, `git status` and
the like — go through without a question. The rest asks. See
[the shell](#the-shell) below.

A rule file decides per tool and per pattern:

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

`pattern` is a glob for the path tools (`*` in one segment, `**` across
directories), a **regular expression** for `bash`, and the tool name for
everything else. For `bash` the pattern is matched against the **beginning of
each part** of the command: `git push` matches `git push origin main`, and it
does not match `echo "git push"`.

```bash
coder -t "run the tests" --permission-mode acceptEdits
coder -t "how would you fix this?" --permission-mode plan
```

`plan` and `readonly` put a note into the messages the model sees:

```xml
<permission_mode mode="plan">
You are in plan mode. You may only look around: `read`, `glob`, `grep` and `ls`
work, but every tool that changes something, `bash` included, is refused.
Investigate the task and answer with the plan you would follow. The user
decides whether it is executed.
</permission_mode>
```

`Always allow` at an approval writes a rule into `~/.coderagent/rules.yaml`:

```yaml
rules:
  - tool: bash
    pattern: pytest
    decision: allow
    reason: always allowed by the user
```

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `Error: permission denied for 'write'. '{path}' is outside the working directory {cwd}` | The agent tried to touch a path outside the working directory. | Add the directory to `permissions.include_dirs`, or change the working directory. |
| `Error: the user denied 'write'.` | Somebody refused the approval. | Allow it, or write a rule for it. |
| `Error: 'write' needs approval but no approver is available. Run with --permission-mode bypass to allow it.` | The run had no terminal (a script or a CI job) and the tool needed approval. | `--permission-mode bypass`, or a rule with `decision: allow`. |
| `{path}:{line}: invalid decision '{d}', expected one of allow, ask, deny` | The rule file has a wrong decision. | Use `allow`, `ask` or `deny`. |
| `{path}:{line}: unknown rule keys: {keys}` | The rule has a key that does not exist. | The keys are `tool`, `pattern`, `decision` and `reason`. |
| `{path}: invalid YAML: {error}` | The rule file cannot be parsed. | Fix the YAML; the message has the line. |
| `{path}: \`rules\` must be a list` | The `rules` key is not a list. | Make it a list of mappings. |
| `Error: permission denied for 'bash'. '{path}' is outside the working directory {cwd}` | The command names a path outside the working directory. | Use a path inside it, or open the directory with `permissions.include_dirs`. |

A rule with `decision: allow` does **not** open the disk: a path outside the
working directory stays outside, unless it is in `permissions.include_dirs`.
The rules of the user cannot widen the bounds.

Among the rules that match, the **strictest** one wins. A `deny` is never
undone by a later `allow` — the rules of the project may only deny, and that
deny holds against the rules of the user. Between `allow` and `ask` the last
matching rule wins.

`permissions.deny_paths` denies everything that matches, and it is applied
after the rule files, so it wins over an `allow` of the same path. A denied
path is off limits for the shell as well: with `*.env` denied, `cat .env` is
refused just like `read .env` is.

### The shell

The `bash` tool is the one that can do anything, so it has three boundaries.

**The commands that only look around go through.** `ls`, `cat`, `head`, `tail`,
`grep`, `diff`, `wc`, `jq` and the reading commands of `git` (`status`, `diff`,
`log`, `show`, …) are safe: they do not change anything and they do not reach
the network. They do not ask.

**The commands that destroy something or send it out ask.** `rm`, `mv`, `cp`,
`chmod`, `curl`, `wget`, `ssh`, `pip`, `npm`, `docker`, `git push` and the
like. They are not refused — a person decides, and the approval says what the
command does ("sends data out of the machine"). In `bypass` they go through
like everything else, because nobody is there to ask.

**A path outside the working directory is refused.** `cat /etc/passwd`,
`cat ../secret`, `cat ~/.ssh/id_rsa` and `cd ..` are denied in every mode,
like the paths of the file tools. The programs of the system may be named
(`/bin/ls`), the data may not leave the working directory. `permissions.include_dirs`
opens a directory outside it.

Every part of a command is judged on its own, and the strictest part wins: an
allowed `pytest` does not carry a `rm` along with it.

The paths of a command are the ones it names, variables and all: `cat
$HOME/.ssh/id_rsa` is refused like `cat ~/.ssh/id_rsa`, and an assignment in
the command is seen by the words after it (`DIR=/etc cat $DIR/passwd`). A
substitution runs a command too: `echo $(rm -rf ~)` is as dangerous as
`rm -rf ~`.

```bash
ls -la                       # goes through
git status                   # goes through
curl http://example.com      # asks: sends data out of the machine
pytest -q && rm -rf build    # asks: the rm is dangerous
cat /etc/passwd              # refused
```

## The sessions

- **New, listed, continued, copied** — `--resume`, `--continue`, `--fork` and
  `--list`.
- **The event log is the truth** — every message, tool call, result and cost
  is appended to a JSONL file. A session is rebuilt by replaying it.
- **A killed session is repaired** — a tool call whose result never came back
  gets one that says so, so the session can be continued. A `/rewind` that
  drops a result is repaired the same way.
- **Checkpoints** — a snapshot of the file before every write. `/rewind` rolls
  back to one.
- **`/clear`** — starts a new session and keeps the old one in the log.
- **A name, a place to put it, a way to remove it** — `/rename`, `/archive`
  and `/delete`. An archived session is not in the list of `/resume`, but it is
  still there.
- **The history may be kept or not** — `history.persistence: save-none` keeps
  the sessions in the memory, `history.max_bytes` deletes the oldest ones when
  the history grows over it. The running session is never one of them.
- **The money** — tokens and cost per session, in the status bar, in `/cost`
  and in the trace.
- **A model without a price** — the money is unknown, not zero: the status bar,
  `/cost` and the list of the sessions show `$?` instead of a price. The budget
  of such a model is `agent.token_limit`.
- **The trace** — `coder export --format json|otel` writes the session out,
  for a dashboard or for OpenTelemetry.

### The trace of a session

The trace is the event log with the metrics of the session. `coder export`
writes it to a file, and `telemetry.otel_endpoint` sends it to a collector:

```yaml
telemetry:
  otel_endpoint: "http://localhost:4318/v1/traces"
  otel_headers:
    authorization: "Bearer …"
```

- **One span per turn, one per model call, one per tool call** — the calls of
  a turn are the children of that turn;
- **The money is on the spans** — `turn.cost`, `cost`, `tokens.in` and
  `tokens.out`;
- **Every span is sent once**, when the turn ends;
- **A backend that is down is a warning** — the session goes on, and the trace
  is sent again with the next turn;
- **The event log stays the truth** — the trace is built from it, and the log
  is written whether the backend is there or not;
- **A project may not send the trace somewhere** — it may close the trace
  (`otel_endpoint: ""`), never point it at an address of its own.

`coder export --format otel --push` sends one session by hand. See
[Trace export](coderagent_export.md).

### Example

```bash
coder -t "first task"                     # a new session
coder --list                              # the sessions of this directory
coder --resume 20261109-3f0a91 -t "more"  # continue that one
coder --continue -t "more"                # continue the newest of this directory
coder --fork 20261109-3f0a91 -t "other"   # a copy, the original stays
```

The files of a session live in `~/.coderagent/`:

```
~/.coderagent/sessions/20261109-3f0a91.jsonl        # the event log
~/.coderagent/sessions/20261109-3f0a91.meta.json    # id, cwd, created_at, model_name
~/.coderagent/checkpoints/20261109-3f0a91.json       # the snapshots of the writes
```

The event log is one JSON object per line, and the types are `user_message`,
`assistant_message`, `tool_call`, `tool_result`, `approval_request`,
`approval_response`, `state_change`, `compaction`, `reflection`, `verify`,
`reverted_to`, `error` and `turn_end`.

`/rewind` restores the **files** only — what a command did to the outside
world stays done — and truncates the history of the session to the moment of
the snapshot.

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `ValueError: no checkpoint '<id>' in this session` | `/rewind` was given an id that is not a checkpoint of this session. | `/rewind` without an id lists the checkpoints. |
| `/resume <unknown id>` starts a session with the directory `.` | A session id that is not in the log does not fail — it makes an empty session. | Check the ids with `coder --list`. |
| A turn ends with `stop_reason: max_turns` | The agent made 100 model calls (`agent.max_turns`) without finishing. | Raise `agent.max_turns`, or make the task smaller. |
| The agent goes quiet without an answer | The turn was cut off: at the ceiling of the model calls, at the budget, or at the token limit. The interface says so under the last answer. | Raise the ceiling that the line names (`agent.max_turns` and the like), or make the task smaller. |
| A turn ends with `stop_reason: cost_exceeded` | The turn cost more than `agent.cost_limit`. `0` means no limit. | Raise `agent.cost_limit`. |
| A turn ends with `stop_reason: token_limit` | The turn used more tokens than `agent.token_limit`. `0` means no limit. This is the budget of a model that has no price, where the money never moves. | Raise `agent.token_limit`. |
| A turn ends with `stop_reason: error` | The model call failed after the retries. The text of the error is in `error`. | Look at `error`; it is the message of the provider. |
| A turn ends with `stop_reason: interrupted` | Somebody pressed `ctrl+c`. | The session is saved; continue it with `--resume`. |
| The trace does not arrive at the backend | The backend refused it or is not there. The reason is in the log of the agent. | Check `telemetry.otel_endpoint` and the headers. |

A turn that ended with `cost_exceeded` or `error` is **not** reflected on: the
memory of the session keeps what was learned before the failure.

## The context

- **The tokens are counted** — with tiktoken when it is installed, otherwise
  an estimate.
- **The window follows the model** — 64k for DeepSeek, 200k for Claude, 128k
  for GPT, and so on. A configured `context_window` wins over the table.
- **Automatic compression** — when the conversation reaches 80 % of the
  window, it is summarized and the history is shortened. The summary is a
  structure: goal, findings, decisions, files touched, open questions, next
  steps, errors seen.
- **What is kept** — the last turns, or the last 40 % of the tokens, whichever
  is more.
- **`/compact`** — compress on demand.
- **`/recap`** — summarize the conversation without dropping anything: the
  summary is for you to read, the model still sees the whole conversation.
- **The order of the messages** — system prompt, the instruction files, the
  todo list, the summary of the session, then the history.
- **The instruction files are cut** — one file may take 32768 bytes
  (`context.project_doc_max_bytes`). A longer file is cut short, and the agent
  is told that it did not see all of it. The memory files are cut the same way.

### Example

```yaml
context:
  context_window: 64000
  compact_threshold: 0.8
  keep_recent_turns: 20
  keep_recent_token_ratio: 0.4
  compact_every_turns: 40
  summarize_model: deepseek/deepseek-flash
```

Without `context_window` in the configuration the window follows the name of
the model: `gpt-` 128k, `claude` 200k, `deepseek` 64k, `qwen` 32k, `llama` 8k,
`gemini` 1M, `mistral` 32k, `kimi` 256k, `minimax` 200k, and 200k for
everything else.

The summary is a JSON object with these keys:

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

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `... (nothing left to compact)` | The turn failed because the context was too big and there was nothing left to shorten. | Raise `context.context_window`, lower `context.reserved_output`, or `/clear` and start over. |
| The summary is a fallback instead of the real thing | The model answered with something that is not the JSON of the summary. It is tried twice, and the second time a conservative summary is used: the last five messages, with `next_steps: ["re-read the files that were mentioned to recover the details"]`. The summary of the round before is merged into it, so the session does not lose its memory. | Nothing to do — the session continues. Ask the model again for the details it lost. |
| The summary does not name the files that were changed | The model did not say what it touched. The files are taken from the messages instead, which know the truth. | Nothing to do. |
| `recent_errors` is empty although the session had errors | Only the tool messages that start with `Error:` are collected, and only the last three of them. | Nothing to do. |

The token count is exact with tiktoken and an estimate without it:
`int(chars / 3.6) + 4 * len(messages)`. An estimate that is too small delays
the compression, so installing tiktoken is worth it for a long session.

## The memory

- **The memory of the project** — `.coderagent/memory`, written at the end of
  a turn with what was learned about the project.
- **The memory of the user** — `~/.coderagent/CLAUDE.md`, with the
  preferences of the user.
- **Preferences wait for a confirmation** — they land in
  `pending-memory.md` first, and `/memory confirm` writes them.
- **The instruction files** — `AGENTS.md` and `CLAUDE.md` of the repository and
  of the project, and the `CLAUDE.md` of the user, are read by the agent. The
  rules of the repository are read even when the agent starts in a
  subdirectory of it.
- **It can be switched off** — `memory.enabled`.

### Example

The three files:

```
.coderagent/memory/projects.md        # what the agent learned about the project
.coderagent/pending-memory.md         # the preferences, waiting for a confirmation
~/.coderagent/CLAUDE.md                # the preferences that were confirmed
```

At the end of a turn the agent looks at the last 40 messages and writes what
it found:

```markdown
# Project memory

- the tests of the API are run with `pytest tests/`, they need a postgres on localhost
- the release is made with `bump2version`, not with a manual edit of setup.py
```

A preference of the user goes to `pending-memory.md` first:

```markdown
# Preferences waiting for a confirmation

- always answer in Chinese
```

and only lands in `~/.coderagent/CLAUDE.md` after `/memory confirm`:

```markdown
## Preferences

- always answer in Chinese
```

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `The memory was not written: {path} would grow past 200 lines; tidy it up first.` | The file would become longer than 200 lines. | Shorten the file, or split it. |
| `The reflection of the session failed` (a warning in the log) | The model did not answer with the expected JSON, so nothing was written. The session is not harmed. | Nothing to do; the next turn tries again. |
| `Wrote 2 preference(s) to /Users/you/.coderagent/CLAUDE.md.` | The confirmation worked. | — |
| `Nothing like that in the memory.` | `/memory forget` did not find the text. | Check the text with `/memory`. |
| `Removed.` | `/memory forget` removed the text. | — |

The memory can be switched off entirely:

```yaml
memory:
  enabled: false
```

## The extensions

- **Sub agents** — `.coderagent/agents/*.md`: a name, a description, a system
  prompt, a list of tools and a maximum number of turns. `code-explorer`,
  `verifier` and `refactorer` come with the agent. The model sees the index
  of them, so it can call them by name.
- **Skills** — `.coderagent/skills/<name>/SKILL.md`: a package of steps,
  scripts and templates for a kind of task. The agent loads one when it fits.
- **Plugins** — `.coderagent/plugins`: a Python module that adds tools,
  commands and hooks. A plugin has to be trusted once.
- **Hooks** — nine moments: `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
  `PostToolUse`, `Stop`, `SessionEnd`, `PreCompact`, `PostCompact` and
  `SubagentStop`. A hook is a command that reads JSON and answers JSON: allow,
  deny or block, with a reason, with extra context or with rewritten arguments.
- **Your own commands** — `.coderagent/commands/*.md` and
  `~/.coderagent/commands/*.md`: a slash command with a description, an
  argument hint, the tools it may use and its own model. The command of the
  project wins when both have the same name.
- **The tools of a command may be limited** — `allowed-tools: bash(git diff:*),
  read` means: the command may read and it may run `git diff`, and nothing
  else. The limit holds in every permission mode.
- **MCP servers** — a server over stdio. Its tools join the
  tools of the agent, they ask for permission like every other tool, and the
  connection is made again when it breaks.
- **The code of a project waits** — an MCP server, a hook or a verify command
  that the project defines runs a program without asking, so it waits for a
  decision of the user: `/trust` shows what waits, `/trust 1` trusts it. The
  decision belongs to the command: a command that changes is trusted again.
- **The project may only take tools away** — the mode of a project may only be
  `plan` or `readonly`, its rules may only deny, its denied paths are added to
  the ones of the user, and the tools it names may only remove from the tools
  of the user. It may also not choose the programs that would run on the
  machine of the user: the editor, the notifier and the environment of the
  sandbox are the decision of the user.

### Example

A sub agent, `.coderagent/agents/scout.md`:

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

The model calls it as a tool:

```json
{"tool": "task", "params": {"subagent_type": "scout", "description": "where is the auth?", "prompt": "find the auth code"}}
```

and the answer is a JSON object:

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

A skill, `.coderagent/skills/release/SKILL.md`:

```markdown
---
name: release
description: How to make a release of this project
---

1. Run the test suite.
2. Run `bump2version patch`.
3. Push the tag.
```

A hook, in the configuration:

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

The hook reads JSON on stdin and answers JSON on stdout:

```json
{"decision": "block", "reason": "the command writes a secret"}
```

`decision` is `allow`, `deny` or `block`; the hook may also add
`additionalContext` or rewrite the call with `updatedInput`. For a tool the
new input is a mapping of arguments; the `UserPromptSubmit` hook rewrites the
prompt of the user with a string.

A custom command, `.coderagent/commands/commit.md`:

```markdown
---
description: Make a commit of the changes
argument-hint: [message]
allowed-tools: bash(git diff:*), read
model: cheap
---

Commit everything with the message: $ARGUMENTS
```

The pattern of a tool is a limit of its own: `bash(git diff:*)` lets the
command run `git diff` and nothing else, and a rule of the user cannot widen
it. A tool that is not named is not there at all.

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `Error: unknown sub agent 'scout'. Available sub agents: code-explorer, refactorer, verifier.` | The name of the sub agent is not in the index. | Use one of the listed names; the index of the custom ones is in the system prompt. |
| `Error: the sub agents are not available in this session.` | The `task` tool is not registered — `tools.enabled` was narrowed. | Put `task` back into `tools.enabled`. |
| `Error: unknown skill 'release'. Available skills: {...}.` | The skill does not exist. | The skills are `.coderagent/skills/<name>/SKILL.md`. |
| `Trusted 'x'. It is loaded the next time the agent starts.` | The answer of `/plugins trust x`. | The plugin is used from the next session. |
| `Error: the hook blocked 'bash'. the command writes a secret` | A `PreToolUse` hook refused the call. | Fix the command, or fix the hook. |
| `Hook 'check_secrets.sh' timed out, ignoring it` | The hook took longer than its timeout. The call goes through. | Raise the `timeout`, or make the hook faster. |
| `Hook 'check_secrets.sh' failed with RuntimeError: ...` | The hook crashed. The call goes through. | Fix the hook. With `strict: true` the call is blocked instead. |
| `Error: the MCP server 'echo' is not connected.` | The server is not running. | Check the `command` or the `url` of the server; `/mcp` says `connected`, `failed: <error>` or `no command and no url`. |
| `Error: the MCP tool 'echo' failed: RuntimeError: ...` | The server answered with an error. The name in the message is the one of the server. | The message of the server is in the answer. |

The custom commands are looked up in `<cwd>/.coderagent/commands/*.md` and in
`~/.coderagent/commands/*.md` — the agent does not walk up the directories to
find them. The command of the project wins when both have the same name.

## The sandbox

- **Local by default** — the commands run in the working directory.
- **Or in a container** — `docker`, `singularity`, `bubblewrap`, `contree`,
  and the remote sandboxes of SWE-rex. The same environments as
  mini-swe-agent.
- **Three modes** — `sandbox.mode` is `full-access` (the default),
  `workspace-write` or `read-only`. The operating system enforces them:
  Seatbelt on macOS, bubblewrap on Linux.
- **Only `bash` goes into the sandbox** — the file tools stay in the working
  directory. In the `read-only` mode they are refused as well.
- **`/sandbox`** — says where the commands run.

### Example

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
```

The seven types are `local`, `docker`, `singularity`, `bubblewrap`, `contree`,
`swerex_docker` and `swerex_modal`. The options that the environment does not
know are ignored, so one file can carry the settings of several of them.

The mode belongs to the local sandbox, and it is a second axis next to the
permission mode: the permissions ask the user, the sandbox asks nobody.

```yaml
sandbox:
  type: local
  mode: workspace-write
```

`/sandbox` answers with the type, the mode, the options that are in effect and
the environment that is in use:

```
type: local
mode: workspace-write
environment: local/workspace-write
```

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `ValueError: Unknown environment type: nope (resolved to nope, available: {...})` | The type is not one of the seven. | Use one of the names above. |
| `CalledProcessError: Command '[...]' returned non-zero exit status 1.` | The container could not be started, or the image could not be pulled. | Check the image name and that docker runs. |
| `FileNotFoundError: [Errno 2] No such file or directory: 'singularity'` | The binary of the environment is not installed. | Install it, or use another type. |
| `UnsupportedSandbox: The read-only mode needs bubblewrap (bwrap), which this machine does not have.` | The machine has no program that builds the sandbox. | Install bubblewrap, or use `full-access`. |
| The file tools touch the files of the host | Only `bash` goes into the sandbox. | That is by design: `read`, `edit` and friends work on the working directory of the session. |

## The verification

- **Off by default** — nothing is checked unless `verify.commands` is set.
- **The agent has to make the check pass** — when the model wants to stop, the
  commands run; if one of them fails, the agent gets the output and tries again.
- **The commands run in the session** — they are your commands, not the agent's,
  so they run as you, without a permission check and without an approval.
- **A bounded number of rounds** — `verify.max_rounds` (3 by default). When the
  rounds are used up, the turn ends with `stop_reason: verify_failed`.
- **The result is in the log** — an event of the type `verify` holds the commands
  and the ones that did not pass.

### When the commands run

The commands run when the agent wants to stop: it answers without a tool call.
They do not run after every tool call, so an agent that keeps working is never
checked. The order of the gates is the `Stop` hook, then these commands, then
the schema of the answer.

The commands are the **user's**, not the agent's, so they run:

- without a permission check — the rules of `permissions` do not see them,
- without a hook — `PreToolUse` and `PostToolUse` are not called for them,
- without an approval — nobody is asked,
- without the confinement of `sandbox.mode` — that one reaches the `bash` tool
  only; the commands go straight to the environment of the session.

They run in the environment of the session. With `sandbox.type: local` that is
the working directory of the session; with a container it is the working
directory of the environment, which is `/` unless the environment is given
another one. A container or a bubblewrap still holds them: there the
environment is the boundary, not `sandbox.mode`.

A verification command of a **project** waits for a decision of the user, like
the other code of a project. An untrusted one is left out of the
configuration, so the verification does not happen at all — and nothing says so.

### The rounds

`verify.max_rounds` (3 by default) is the number of times the commands run.
The agent is told about a failure and gets to fix it, so with three rounds it
is corrected twice; when the third run fails too, the turn ends with
`stop_reason: verify_failed` and the message is in `error`.

The commands all run, one after the other, and every one that failed is
reported. A command that times out counts as a failure, with the exit code
`-1`.

The output of a command is trimmed to 2000 tokens before it goes back to the
model: the head and the tail are kept, the middle is elided, and a marker says
how much is missing.

### Example

```yaml
verify:
  commands:
    - python -m pytest -q
  max_rounds: 3
  timeout: 300
```

When the model says it is done and the tests do not pass, the agent gets this
back and keeps working:

```
[verify] These commands did not pass. Fix the problem and try again.

$ python -m pytest -q
2 failed, 1 passed
[exit code 1]
```

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| The turn ends with `stop_reason: verify_failed` | The commands still failed after `verify.max_rounds` rounds. | Read the output of the last round in the event log. |
| The check runs in the sandbox and cannot find the files | The sandbox does not have the working directory of the session. | Give the environment a working directory, or use `local`. |
| The check takes too long | The command was killed after `verify.timeout` seconds. | Raise `verify.timeout`. |
| The agent keeps fixing the same thing | The check needs something the agent cannot do. | Fix the check or the task. |

## The terminal interface

- **The answer streams in** — the text and the reasoning.
- **The status bar** — the model, the tokens, the cost, the directory and the
  permission mode.
- **The tool cards** — the call, the output and the diff of the change.
- **The approval** — `y`, `n` and `a`, or the arrow keys on a numbered list.
- **Long output is folded away** — the interesting part stays visible.
- **The todo panel** — the task list of the current work.
- **The commands have a place of their own** — the line you typed and the answer
  of the command are messages of their own; the answer of the agent stays.
- **The input has a history** — `↑` and `↓` walk through the messages you sent,
  the way a shell does; walking past the newest one gives your draft back.
- **A file is mentioned with `@`** — type `@src/app` and the path of the file is
  completed; `→` takes the completion.
- **A panel of the sessions** — `ctrl+o` lists the sessions of this directory;
  `enter` continues the one that is picked, `escape` closes the panel.
- **A tree of the files** — `ctrl+t` opens it on the left: the files of the
  directories the user opened to the agent (`permissions.include_dirs`; the
  working directory when there are none), three levels deep, with the ones that
  changed marked (`+` added, `●` changed, `-` deleted, `?` new). Picking a file
  puts its path in the input.
- **The terminal is told when a turn is over** — a notification with the answer
  of the agent, so a long turn is not missed. `ui.notifications: false` turns it off.
- **A program of your own may say it** — `ui.notify_command` names a program that
  is called with the title and the body of the notification, e.g. `notify-send`.
  A program that fails is a warning, not a broken session. A project may not
  choose the notifier: that program runs on the machine of the user.
- **The answer is Markdown** — the code blocks, the tables and the lists look the
  way they look in the README of a project. The text is plain while it arrives and
  is rendered when it is complete; `ui.markdown: false` keeps it plain.
- **A picture can be sent** — `/image shot.png what is this` sends the picture
  with the text that goes with it.
- **A file opens in your editor** — `/open src/app.py` opens it in the program
  of `ui.file_opener` (`vscode`, `cursor`, `windsurf`, or a command of your own).
  A project may not choose the editor.
- **`ctrl+c` stops the tool that is running** — not only the turn: a command that
  runs in the shell is stopped, together with the processes it started. It also
  cuts the answer of the model short: the turn ends while the model is still
  writing, and the half answer is not kept.

### Example

The status bar looks like this:

```
deepseek/deepseek-flash | 1.5k/64k | $0.0000 | ~/work/project | default
```

An approval is a numbered list, and the selected one is marked:

```
1 [*] y allow
2 [-] n deny
3 [-] a always allow
```

`←`/`→` move the cursor, `↑`/`↓` do the same, the digits jump to a line, the
space toggles a multiple choice, `enter` confirms, and `y`, `n` and `a` answer
directly. `ctrl+c` interrupts the turn, `ctrl+q` settles the session and quits,
`ctrl+o` opens the panel of the sessions, `ctrl+t` opens the tree of the files.

The todo panel marks the state of a task with `◉` (completed), `◐` (in progress)
and `○` (pending).

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| Nothing happens when a tool wants approval | The terminal is not there — the run is headless. | The call is denied. Use `--permission-mode bypass` or a rule. |
| `▸ 42 more lines` under the output of a tool | The output was longer than the card. | The interesting part is visible; open the file, or run the command again with less output. |
| The interface does not start | `coder` without a task in a terminal starts the interface; without a terminal it prints `no task given`. | Use `coder --tui` to force it. |
| `The agent is working. Wait for it, or press ctrl+c to stop it.` | A command was typed while the agent was in the middle of a turn. The command did not run. | Wait for the turn to end, or press `ctrl+c` to stop the agent. |
| `shot.png is too big: 7000 KB, the limit is 5120 KB` | The picture is bigger than the limit of 5 MB. | Make the picture smaller, or send it as a file the agent can read. |

## The web interface

- **The chat page** — three columns: the sessions and the files on the left,
  the conversation in the middle, the status, the changes and the file on the
  right.
- **The answer streams in** — over a server sent event stream, and a browser
  that comes late reads the whole answer.
- **The settings page** — the model as a form, the layer every field comes
  from, the preview of all the layers with the secrets taken out.
- **Test the connection** — one cheap call, and it says whether the model
  calls the tools at all.
- **Test a model** — a panel for an endpoint, a key and a model name, without
  writing anything.
- **The permissions in two places** — the settings page for the next
  session, the chat page for the session that is running, right away.
- **The approvals in the browser** — the same three answers.
- **The languages** — English and Chinese. The switch in the top bar changes
  the whole page without a reload, and the choice is remembered in the
  browser and in a cookie. The region of the address decides when the
  visitor has not chosen.
- **The security model** — no authentication, `127.0.0.1` by default, a
  header that a cross site request cannot send, a path that cannot leave the
  working directory, and a key that is only shown when it is asked for.

### Example

```bash
coder web --cwd . --port 8765
```

```
coder web: http://127.0.0.1:8765
```

The API is plain HTTP. A message to a session:

```bash
curl -X POST http://127.0.0.1:8765/api/sessions/20261109-3f0a91/messages \
  -H 'X-Coder-Client: 1' -H 'Content-Type: application/json' \
  -d '{"text": "run the tests"}'
```

The stream of the events of a session:

```bash
curl -N http://127.0.0.1:8765/api/sessions/20261109-3f0a91/stream
```

The endpoints of the API:

| Endpoint | What it does |
|---|---|
| `GET /api/sessions` | The sessions of the working directory |
| `POST /api/sessions` | A new session |
| `GET /api/sessions/{id}` | One session |
| `GET /api/sessions/{id}/events` | The events of the session |
| `GET /api/sessions/{id}/items` | The items of the session after a sequence number |
| `GET /api/sessions/{id}/stream` | The stream of the events (SSE) |
| `GET /api/sessions/{id}/status` | The state, the model, the tokens, the cost |
| `GET /api/sessions/{id}/metrics` | The metrics of the session |
| `GET /api/sessions/{id}/changes` | The files that were changed |
| `POST /api/sessions/{id}/resume` | Continue the session |
| `POST /api/sessions/{id}/fork` | A copy of the session |
| `POST /api/sessions/{id}/messages` | Send a message |
| `POST /api/sessions/{id}/review` | Review the changes of the project |
| `POST /api/sessions/{id}/interrupt` | Interrupt the turn |
| `POST /api/sessions/{id}/mode` | Change the permission mode of the session |
| `POST /api/approvals/{id}` | Answer an approval |
| `GET /api/commands` | The slash commands |
| `GET /api/config` | The configuration and its layers |
| `PUT /api/config/model` | Write the model to the user level file |
| `GET /api/config/model/key` | The key of the endpoint |
| `PUT /api/config/permissions` | Write the permissions to the user level file |
| `POST /api/config/model/test` | One cheap call to test the model |
| `GET /api/files` | The files of the working directory |
| `GET /api/file` | One file |
| `GET /api/diff` | The diff of one file |
| `GET /api/i18n/{language}` | The strings of a language |

### When something goes wrong

| Status | Message | What it means | What to do |
|---|---|---|---|
| 403 | `the X-Coder-Client header is missing` | A write without the header. A browser on another site cannot send it. | Add `-H 'X-Coder-Client: 1'`. |
| 404 | `there is no session with the id {id}` | The id is unknown. | `GET /api/sessions` for the list. |
| 404 | `no approval is waiting for the id {id}` | The approval was answered already, or it timed out. | Nothing to do. |
| 404 | `unknown language` | The language of `/api/i18n/{language}` is not one of the ones that are on. | Use `en` or `zh`. |
| 400 | `the message is empty` | The message has no text. | Send a text. |
| 400 | `unknown permission mode '{value}'` | The mode is not one of the five. | Use `default`, `acceptEdits`, `plan`, `readonly` or `bypass`. |
| 400 | `the decision must be allow, deny or always` | The answer of an approval is wrong. | Use `allow`, `deny` or `always`. |
| 400 | `'{path}' is not a directory` | A path of the file API is a file. | Use a directory. |
| 403 | `'{path}' is outside the working directory {cwd}` | The path leaves the working directory. | Nothing — that is the boundary. |
| 409 | `the session {id} is running` | The session is busy, so it cannot be forked or resumed. | Wait for the turn to end, or interrupt it. |

The approval that nobody answered is denied after `ui.approval_timeout`
seconds, and the browser is told `timed_out: true`.

An approval of a tool that changes a file writes a rule into
`~/.coderagent/rules.yaml` — the same file the terminal uses.

The address of the server is printed on the start. With `--host 0.0.0.0` the
server warns:

```
The web interface listens on 0.0.0.0: everybody who can reach that address can drive the agent.
```

## The configuration

- **Five layers** — the defaults of the package, the project file
  `.coderagent/config.yaml`, the user file `~/.coderagent/config.yaml`, the
  profile that is in effect, and the overrides of the command line
  (`-c key=value`). The later wins.
- **The sections** — `model`, `agent`, `tools`, `permissions`, `context`,
  `memory`, `checkpoint`, `mcp`, `hooks`, `ui`, `sandbox`, `verify`,
  `telemetry`, `shell_environment` and `history`, plus `profiles` and `profile`.
- **The paths** — `MSWEA_CODER_HOME` moves the user level files somewhere
  else.
- **The settings page writes the user file only** — the project file is in
  the repository and is never written.

### Example

```bash
# A file.
coder -t "..." -c myconf.yaml
# Overrides, repeatable.
coder -t "..." -c model.model_name=deepseek/deepseek-chat -c agent.max_turns=20
```

The layers, from the lowest to the highest priority:

1. the defaults of the package (`src/coderagent/config/defaults.yaml`),
2. `.coderagent/config.yaml` of the project,
3. `~/.coderagent/config.yaml` of the user,
4. the profile that is in effect,
5. the `-c` of the command line.

The model name is looked up in this order: the `-c` of the command line, the
profile, the user file, `$MSWEA_MODEL_NAME`, and at the end
`anthropic/claude-sonnet-4-5`. A **project may not choose the model**: the whole
`model` section of a project is dropped, because the endpoint of a project
would take the conversation — and the key of the user with it — somewhere else.
The same holds for the two other places where a model is named:
`context.summarize_model` of a project is dropped, and a command of the project
may not name a model.

A **project may not put variables into the environment of the agent**: the
`shell_environment.set` of a project is dropped, because a `LD_PRELOAD` or a
`PATH` of its own would run the code of the repository on the machine of the
user, in every command the agent runs. A project may not claim a context
window bigger than the one of the model either. The **ceilings of the
session** — `agent.max_turns`, `agent.cost_limit`, `agent.token_limit`,
`agent.subagent_max_turns`, `agent.subagent_max_parallel`,
`tools.bash_timeout` and `tools.max_output_tokens` — a project may only
**lower**: a higher one is given the default instead. A ceiling that you name
yourself is yours, so your file, a profile and the command line win over the
project.

### The profiles

A profile is a named piece of configuration. It is chosen with `--profile` (or
`-p`), and it sits above the user file and below the `-c` of the command line:

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

The name of the profile can also stand in the configuration itself:

```yaml
profile: fast
```

A **project** may neither define a profile nor choose one: the profiles of a
project are dropped, like every other piece of code that comes with a
repository. Choosing a set of permissions is the decision of the user.

The tightening of the project still wins: a project that closes the sandbox
(`sandbox.mode: read-only`) keeps it closed, even when the profile says
`full-access`. A project may not say *where* the commands run: the `type` of
the sandbox and the options of the environment are dropped from the
configuration of a project.

The sections and what they hold:

| Section | The keys |
|---|---|
| `model` | `model_name`, `api_key`, `api_base`, `model_kwargs`, `max_retries`, `litellm_config`, `routing`, `routing_rules`, `set_cache_control`, `reasoning_effort`, `verbosity`, `review_model` |
| `agent` | `system_prompt`, `max_turns`, `cost_limit`, `token_limit`, `subagent_max_turns`, `subagent_max_parallel` |
| `tools` | `enabled`, `disabled`, `bash_timeout`, `max_output_tokens`, `schema_budget_tokens` |
| `permissions` | `mode`, `rules`, `deny_paths`, `include_dirs`, `network` |
| `context` | `context_window`, `reserved_output`, `compact_threshold`, `keep_recent_turns`, `keep_recent_token_ratio`, `compact_every_turns`, `auto_compact`, `summarize_model`, `summary_chunk_tokens`, `project_doc_max_bytes` |
| `memory` | `project_path`, `user_path`, `enabled` |
| `checkpoint` | `enabled`, `keep` |
| `mcp` | `servers`, `timeout` |
| `hooks` | `events` |
| `ui` | `approval_timeout`, `notifications`, `notify_command`, `markdown`, `file_opener` |
| `shell_environment` | `inherit`, `exclude`, `include`, `set` |
| `sandbox` | `type`, `mode` and the options of the environment |
| `verify` | `commands`, `max_rounds`, `timeout` |
| `telemetry` | `otel_endpoint`, `otel_headers`, `otel_timeout` |
| `history` | `persistence`, `max_bytes` |
| `profiles` | The named pieces of configuration. `--profile` picks one of them |
| `profile` | The name of the profile that is in effect |

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| Nothing happens, the setting is ignored | A key that does not exist is ignored, silently. | Check the spelling against the table above. |
| `yaml.scanner.ScannerError` | The YAML of a layer cannot be parsed. | Fix the YAML; the message has the line. |
| `pydantic_core.ValidationError` | A value has the wrong type — a string where a number belongs. | The message names the field. |
| `FileNotFoundError: Could not find config file for ... (tried: [...])` | `-c myconf.yml` was given, but the file that is looked for is `myconf.yaml`. | Use the name with `.yaml`, or give the full path. |
| The model is not the one in the file | A layer above the file wins. | Remember the order; `--list` of the layers is on the settings page. |
| `ValueError: unknown profile 'slow'. Use one of: fast, careful.` | The name of the profile is not one of the `profiles` of the configuration. | Check the spelling, or add the profile to the file. |

## The commands

Thirty-five built-in commands: `/help`, `/model`, `/mode`, `/plan`,
`/compact`, `/recap`, `/side`, `/clear`, `/resume`, `/fork`, `/rename`, `/archive`, `/delete`,
`/rewind`, `/diff`, `/review`,
`/image`, `/mention`, `/open`, `/init`, `/cost`, `/todos`, `/mcp`, `/permissions`, `/hooks`, `/agents`,
`/skills`, `/plugins`, `/trust`, `/memory`, `/status`, `/sandbox`, `/export`,
`/context` and `/exit` (also `/quit`).

Your own commands live in `.coderagent/commands/*.md` and in
`~/.coderagent/commands/*.md` and join them.

`/help` says what every command takes — the modes of `/mode`, the number of
`/trust`, the arguments of your own commands — so nothing has to be remembered.

### The review

`/review` gives the model the diff and asks it what is wrong with the changes.
Without a range it reviews the working tree; with one (`/review main..HEAD`) it
reviews that range. The files that are new and not in the diff yet are named in
the prompt, so the model reads them when they matter. A diff that is longer
than 60000 characters is cut, and the model is told to read the files itself.

The review is a turn of the current session, with a prompt of its own that says
not to change any file. The answer stays in the conversation.

The diff does not stay in the context: the model reads it during the turn, and
afterwards it is replaced by a note that says the changes are not there any
more and the files have to be read again. A review of a big diff would
otherwise cost the whole session its window.

The review may run on a model of its own: `model.review_model` names it, and
`model.routing.review` wins over that. Without either one the review runs on
the model of the session. The purpose of the turn is in the log, so it can be
read back later.

### The recap and the side conversation

`/recap` summarizes the conversation so far and shows you the summary: the goal,
the findings, the decisions, the files that were touched, the questions that are
still open and the next steps. Nothing is dropped, nothing is compressed, and
the summary does not go into the context of the model — the model still sees the
whole conversation. It is a report for you. The summary costs one call of the
model, and the money is on the session, under the purpose `recap`.

`/side <question>` asks a question in a conversation of its own. The side
conversation is a copy of the current session with a log of its own: the
question and the answer are recorded in the current session, so the agent does
not lose the thread of the work, and nothing else is. The tools the side
conversation uses belong to the side session, and the money it spent is on the
current session, under the purpose `side`.

### The files you mention

A file that is named in the question goes into the message **with its
content**, so that the model does not have to spend a tool call on reading it
again:

```
look at @src/app.py and tell me what it does
```

The mention works in the terminal interface and in the command line alike.
`/mention` does the same thing with an explicit path:

```
/mention src/app.py what does this do
```

The file that is not there is left alone: `@` is used for other things too, in
an address or in a decorator, so only a name that is a file is opened.

The **bounds still hold**: a file outside the working directory, or one that
the rules of the permissions deny, does not go into the message. The message
says that the agent may not read it, instead of smuggling the content in.

Only text goes in: a file that is not text is named and left alone, and an
image goes with `/image`. A file that is longer than 20000 characters is cut,
and the cut is said.

A secret in the file is taken out before the content goes in: the same
redaction as the output of a tool, so a key that sits in a mentioned file does
not end up in the log of the session.

### Example

```bash
coder -t "/cost"          # a command in the terminal
coder -t "/model deepseek/deepseek-chat"
coder -t "/mode plan"
```

A command that takes arguments is the rest of the line:

```
/model deepseek/deepseek-chat
/rewind 20261109-3f0a91
```

In the terminal interface a command is a message of its own: the line you typed
is shown, and the answer of the command does not replace the answer of the
agent. A command is refused while the agent is working.

In the browser the commands are in the palette of the chat page, and the list
comes from `GET /api/commands`.

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `Unknown command '/foo'. Try /help.` | There is no such command. | `/help` lists them; `/help <name>` explains one. |
| `Unknown mode 'bogus'. Use one of: default, acceptEdits, plan, bypass, readonly.` | `/mode` was given a mode that does not exist. The mode of the session is unchanged. | Use one of the five. |
| `/rewind` with an id that is not a checkpoint | `ValueError: no checkpoint '<id>' in this session` | `/rewind` without an id lists the checkpoints. |
| `Not a git repository: {cwd}` | `/diff` runs `git diff`, and this directory is not a repository. | Run it in a repository, or use the changes of the web page. |
| `No changes to review.` | `/review` found nothing to review in the working tree. | Make a change first, or give a range: `/review main..HEAD`. |
| `Git does not know '{revision}'` | `/review` was given a range that git does not know. | Check the range with `git log --oneline`. |
| `{path} already exists.` | `/init` does not overwrite an `AGENTS.md`. | Edit the file yourself. |
| `No sessions yet.` | `/resume` without an id found nothing in this directory. | Run a turn first. |

## The benchmark part of mini-swe-agent

- **`mini`** — a run script: a task, a model, an environment, and a
  trajectory file.
- **SWE-bench** — the whole dataset, in parallel, with a slice and a filter.
- **SWE-bench, one instance** — for a single problem.
- **ProgramBench** — the programming benchmark.
- **The inspector** — reads a trajectory file and shows what the agent did.
- **The environments** — local, docker, singularity, bubblewrap, contree,
  SWE-rex docker and SWE-rex modal.
- **The models** — litellm for most providers, and portkey, openrouter,
  requesty, the text based models and the roulette model besides.

### Example

```bash
mini --model litellm/deepseek/deepseek-flash --environment-class docker \
  --task "the failing test is in test_api.py"

mini-extra swebench --model litellm/deepseek/deepseek-flash --workers 8 \
  --slice 0:100
```

The trajectory of a run is a JSON file with the messages, the tool calls and
the cost of every step; `inspector` reads it.

### When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| The environment cannot be built | The image is missing or the binary of the environment is not installed. | The same errors as the sandbox of the coding agent. |
| The model answers without a tool call | The model of the benchmark is a text based one, or the format of the answer is wrong. | Use a model that speaks the tool protocol, or a model class of the benchmark that wraps it. |

## Where the details are

| Page | What is in it |
|---|---|
| [The coding agent](coderagent.md) | The whole thing, from the first session to the files |
| [The commands](coderagent_commands.md) | Every command and the ones of your own |
| [The web interface](coderagent_web.md) | The chat page, the settings page, the API |
| [Sub agents](coderagent_subagents.md) | Writing a sub agent |
| [Skills](coderagent_skills.md) | Writing a skill |
| [Hooks](coderagent_hooks.md) | The nine moments and what a hook answers |
| [Plugins](coderagent_plugins.md) | Writing a plugin |
| [MCP servers](coderagent_mcp.md) | The configuration of a server |
| [The memory](coderagent_memory.md) | The files and the confirmation |
| [Model routing](coderagent_routing.md) | The purposes and the rules |
| [The sandbox](coderagent_sandbox.md) | The environments |
| [Trace export](coderagent_export.md) | The trace of a session |
| [Quick start](coderagent_quickstart.md) | The first ten minutes (中文) |
