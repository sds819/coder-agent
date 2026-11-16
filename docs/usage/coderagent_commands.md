# The commands of the coding agent

> 中文版：[命令](coderagent_commands_zh.md)

The `coder` command starts an interactive session. Everything that starts with a
slash is a command, everything else is a message for the agent.

```bash
coder                 # the terminal interface
coder --task "fix the failing test"   # one turn, then the answer
coder --task "/help"  # a command without the interface
```

## In the terminal interface

A command is part of the conversation: the line you typed is shown as your own
message, and the answer of the command is a message of its own. The answer of
the agent is not replaced by it.

A command is refused while the agent is working — it says
`The agent is working. Wait for it, or press ctrl+c to stop it.` and the command
does not run. Wait for the turn to end, or press `ctrl+c` to stop the agent.

## The built-in commands

| Command | What it does | What it takes |
|---|---|---|
| `/help` | The list of the commands | `[name]` |
| `/model` (`/m`) | Show or switch the model | `[model-name]` |
| `/mode` | Show or switch the permission mode | `[default\|acceptEdits\|plan\|bypass\|readonly]` |
| `/plan` | Switch to plan mode, where nothing is changed | |
| `/compact` | Compact the conversation now | |
| `/clear` | Start a new session | |
| `/resume` | List the sessions or resume one | `[session-id]` |
| `/fork` | Copy the session into a new one | `[session-id]` |
| `/rewind` | Show the checkpoints or roll back to one | `[checkpoint-id]` |
| `/diff` | Show the changes in the working tree | |
| `/review` | Review the changes, or the changes of a range | `[main..HEAD]` |
| `/image` | Send an image to the agent | `<path> [what to do with it]` |
| `/mention` | Send a file to the agent, with its content | `<path> [what to do with it]` |
| `/init` | Write an `AGENTS.md` for this project | |
| `/cost` | The tokens and the money spent | |
| `/todos` | The task list of the agent | |
| `/mcp` | The MCP servers and their state | |
| `/permissions` | The rules that are in effect | |
| `/hooks` | The hooks that are loaded | |
| `/agents` | The sub agents that are available | |
| `/skills` | The skills that are available | |
| `/plugins` | The plugins, or trust one of them | `[trust <name>]` |
| `/trust` | The code of the project that waits for a decision, or trust it | `[number]` |
| `/memory` | The memory of the project and of the user | `[confirm\|forget <text>]` |
| `/status` | The state of the session | |
| `/sandbox` | Where the commands of the agent run | |
| `/export` | Write the conversation to a file | `[path]` |
| `/context` | The size of the context | |
| `/exit` (`/quit`) | Leave the interface | |

The third column is what `/help` prints: the options of a command are written
there, so nobody has to remember them. `/help <name>` describes one command and
says what it takes. The commands of the project (see below) are in the list
too, with the arguments their file declares.

The money of `/cost` is the money of the session. A new session (`/clear`) starts
at zero, whatever the session before it spent.

`/review` asks the model to look at the changes and say what is wrong with them.
Without a range it reviews the working tree; with one (`/review main..HEAD`) it
reviews that range. The files that are new and not in the diff yet are named, so
the agent reads them when they matter. The review is a turn of the current
session: the answer stays in the conversation, and you can act on it right away
("fix the second one"). The agent is told not to change any file while it
reviews.

`/image` sends a picture to the model. The path is the first word, everything
after it is the text that goes with the picture:

```bash
/image screenshot.png what is wrong with this layout?
```

The image is sent as it is: `png`, `jpg`, `gif` and `webp` are the formats a
provider takes, and a file that is bigger than 5 MB is refused instead of being
sent. The picture costs tokens like a text does, so the size of the context grows
by the size of the image. The answer of the model stays in the conversation, like
the answer of any other turn.

`/mention` sends a **file** to the model, with its content in the message, so
that the model does not have to read it again with a tool call:

```bash
/mention src/app.py what does this do?
```

The same happens when the question names the file itself: `look at @src/app.py`
puts the content of the file in the message. A name that is not a file stays as
it is, so an address or a decorator is not opened.

The bounds of the permissions hold here too: a file outside the working
directory, or one that a rule denies, does not go into the message. The message
says that the agent may not read it.

`/exit` closes the terminal interface, the same way `ctrl+q` does. In the
browser there is nothing to close, so it says that the server keeps running:
stop it with `ctrl+c` in the terminal that started it.

## Your own commands

A command is a markdown file in `.coderagent/commands`. The file starts with a
front matter, the way Claude Code does it:

```markdown
---
description: Generate a commit message
argument-hint: [file]
allowed-tools: bash(git diff:*), read
---
Describe the change of $1.
Everything else: $ARGUMENTS
```

- `$ARGUMENTS` becomes everything the user typed after the command.
- `$1`, `$2`, … become the arguments, one by one.
- `allowed-tools` limits the tools the command may use. The tools of the
  session are back when the command is done.
- `model` picks another model for this command.

The part in parentheses is a **pattern of its own**: `bash(git diff:*)` lets
the command run `git diff` and nothing else, and a tool that is not named is
not there at all. The limit holds in every permission mode, and a rule of the
user cannot widen it.

The command above is used like this:

```bash
/commit src/coderagent/core/loop.py
```

A file without a front matter is ignored. The commands are looked up in
`<cwd>/.coderagent/commands/*.md` and in `~/.coderagent/commands/*.md` — the
agent does not walk up the directories to find them. The command of the
project wins when both have the same name.
