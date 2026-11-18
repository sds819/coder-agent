# Hooks

A hook is a command of the user that runs at an important moment of a session.
A hook can block an action, rewrite its arguments or add something to the
context of the model.

## The configuration

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

| Key | What it is | Default |
|---|---|---|
| `type` | The kind of the hook. Only `command` is implemented | `command` |
| `matcher` | A regular expression of the tool names. Empty means every tool | |
| `command` | The command to run, with the shell, in the directory of the session | |
| `timeout` | How long it may take, in seconds | 10 |
| `strict` | When the hook fails, block the action instead of letting it through | false |

The hooks of the project live in `.coderagent/config.yaml`, the hooks of the
user in `~/.coderagent/config.yaml`. A plugin may bring hooks too. The two
files are merged like the rest of the configuration: the events are merged,
but the list of the hooks of one event is replaced by the list of the user.

A hook of the **project** runs a program without asking the user, so it waits
for a decision first. The hooks of the **user** are the user's own, so they
are used as they are. See
[The code of a project](coderagent.md#the-code-of-a-project).

The matcher is matched against the name of the tool, so it only means
something for `PreToolUse` and `PostToolUse`. Leave it empty for the other
events. It is a **regular expression that is searched, not anchored**: the
name `multi_edit` matches `edit|write`, and the letters are case sensitive, so
`Bash` matches nothing. A matcher that is not a valid regular expression is
logged and matches nothing.

## The moments

| Hook | When | What it can do |
|---|---|---|
| `SessionStart` | The session starts | Nothing. It is a notification |
| `UserPromptSubmit` | After the prompt, before the model | Add context, rewrite the prompt, or block it |
| `PreToolUse` | Before the tool runs | Deny it, or rewrite the arguments |
| `PostToolUse` | After the tool ran | Add context, or block the result |
| `Stop` | The agent wants to stop | Send it back to work |
| `SessionEnd` | The turn ends | Nothing. It is a notification |
| `PreCompact` | Before the history is compacted | Nothing. It is a notification |
| `PostCompact` | After the history was compacted | Nothing. It is a notification |
| `SubagentStop` | After a sub agent is done | Nothing. It is a notification |

`SessionEnd` runs at the end of every turn, not only when the whole session
is over.

Each event has its own payload:

| Hook | What it reads |
|---|---|
| `SessionStart` | `session_id`, `cwd` |
| `UserPromptSubmit` | `prompt` |
| `PreToolUse` | `tool`, `params` |
| `PostToolUse` | `tool`, `params`, `result` |
| `Stop` | `last_message` |
| `SessionEnd` | `session_id`, `turns`, `cost` |
| `PreCompact` | `messages` (the ones that are about to be compacted), `turn` |
| `PostCompact` | `summary`, `messages` (how many), `tokens`, `summary_tokens` |
| `SubagentStop` | `agent`, `status`, `summary`, `files_touched` |

The three new events are **notifications**: they cannot change what happens.
`PreCompact` and `PostCompact` are the place to measure the quality of the
summaries — the first one sees the messages that go away, the second one sees
the summary that comes and how many tokens it took.

## What a hook answers

The hook reads the details on its standard input and writes its answer as JSON
on its standard output:

```python
#!/usr/bin/env python3
import json
import sys

payload = json.load(sys.stdin)
if payload.get("tool") == "bash" and "rm -rf" in payload["params"].get("command", ""):
    print(json.dumps({"decision": "deny", "reason": "that command is not allowed"}))
```

The keys are:

- `decision`: `allow`, `deny` or `block`. Only `deny` and `block` are looked at —
  `allow` has **no effect**, it neither approves the call nor skips the
  permission check.
- `reason`: why. It goes back to the model as the error of the tool.
- `additionalContext`: something for the model to read.
- `updatedInput`: the new input of the moment. For `PreToolUse` it is a
  mapping and it replaces the arguments of the tool. For `UserPromptSubmit` it
  is a string and it replaces the prompt. At `PostToolUse` the tool has already
  run, so a mapping there replaces nothing.

Nothing on the standard output means the hook has no opinion. The output of
several hooks is put together: a `deny` wins over everything, the contexts are
concatenated and the last `updatedInput` wins.

## What the answer does

| The answer | What happens |
|---|---|
| `PreToolUse` denies | The tool call fails, the reason goes back to the model |
| `PreToolUse` rewrites the arguments | The tool runs with the new arguments |
| `PreToolUse` allows | Nothing. The permission check still runs |
| `PostToolUse` denies | The message that goes back to the model becomes an error. The log keeps the result of the tool |
| `PostToolUse` adds context | The context is appended to the result of the tool |
| `UserPromptSubmit` denies | The turn ends with an error, the model is not called |
| `UserPromptSubmit` adds context | The context is appended to the prompt |
| `UserPromptSubmit` rewrites the prompt | The model sees the new prompt, the log keeps both |
| `Stop` denies | The agent goes on, the reason is a new message for it. At most three times per turn |

The `PreToolUse` hook runs **before** the permission check, so the command
that is approved is the command that was rewritten.

## The Stop hook

The `Stop` hook is asked one question: may the agent stop now? The agent wants
to stop when it answers without a tool call. The hook reads the text of that
answer in `last_message` and answers `block` (or `deny`) to send the agent
back to work.

```python
#!/usr/bin/env python3
import json
import sys

payload = json.load(sys.stdin)
if "TODO" in payload.get("last_message", ""):
    print(json.dumps({"decision": "block", "reason": "There are TODOs left. Do them first."}))
```

The reason goes back to the model as a **user** message, prefixed with
`[hook]`. It is advice, not an order: the model may stop again. So the hook is
asked at most **three times per turn** — after that the agent stops whatever
the hook says, and the hook is not called again in that turn.

What the answer does at `Stop`:

| Key | Effect at `Stop` |
|---|---|
| `decision` | Only `block` and `deny` do anything. `allow` has no effect |
| `reason` | Goes back to the model as a new message |
| `additionalContext` | **No effect** — only the reason is used |
| `updatedInput` | **No effect** — there is nothing to rewrite |

A few things that surprise people:

- **The matcher has to be empty.** The matcher is matched against the name of a
  tool, and the payload of `Stop` has no tool in it. A matcher like `bash`
  matches nothing, so the hook is never called — without a word of warning.
  Leave it empty (or `.*`).
- **A sub agent is not stopped by it.** The `Stop` hook is asked by the main
  agent only. A sub agent that wants to stop simply stops; `SubagentStop` is a
  notification and changes nothing.
- **It comes before the other two gates.** The order is `Stop`, then the
  commands of the verification, then the schema of the answer. A stop that the
  hook blocks skips the other two.
- **Every block costs another call of the model.** A blocked stop sends the
  agent back to the model, and the limits of the turn (`max_turns`,
  `cost_limit`, `token_limit`) are checked again before that call. A hook that
  blocks every time can turn a turn into `max_turns`.
- **The three blocks belong to the turn.** The next question of the user starts
  with three again.
- **`strict: true` can keep the agent from stopping.** A `Stop` hook that ends
  with a non-zero exit code denies the stop, so a broken hook keeps the agent
  at work — until the third block, and then the agent stops anyway.

## A hook that rewrites the prompt

```python
#!/usr/bin/env python3
import json
import sys

payload = json.load(sys.stdin)
print(json.dumps({"updatedInput": payload["prompt"] + "\n\nAnswer in English."}))
```

The model never sees the text the user typed, only the rewritten one. The
event log keeps the prompt of the model, so a replay of the session says the
same thing, and the text of the user beside it under `original`. In the web
interface the bubble shows what the user typed, with a line below it that
says what the agent was given.

A hook that answers with a string `updatedInput` at `PreToolUse` changes
nothing: only a mapping replaces the arguments of a tool.

## When a hook fails

A hook that crashes, times out or writes something that is not JSON is ignored:
the action goes on.

`strict: true` changes one thing: a hook that ends with a non-zero exit code
denies the action, and its standard error is the reason. A timeout and a
broken answer are ignored either way.
