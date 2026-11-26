# The sandbox

The commands of the agent run in a sandbox. By default the sandbox is the
machine of the user.

```yaml
sandbox:
  type: local
```

## The remote sandboxes

The sandboxes are the ones of mini-swe-agent, used as they are:

| `sandbox.type` | What it does |
|---|---|
| `local` | The commands run on this machine |
| `docker` | A Docker container |
| `singularity` | A Singularity container |
| `swerex_docker` | A Docker container that SWE-ReX manages |
| `swerex_modal` | A container on Modal |
| `bubblewrap` | A sandbox without root |
| `contree` | A container without root |

The remote sandboxes are the environments that came with mini-swe-agent: the
coding agent does not write containers of its own. They need the packages of the extra
`sandbox`:

```bash
pip install "coder-agent[sandbox] @ git+https://github.com/sds819/coder-agent"
```

Without them the local sandbox still works, and a remote one says which
package is missing.

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
```

The options that the environment does not know are ignored, so the same
configuration works for every kind of sandbox. A full path of a class works as
well, which is the way to use an environment of your own:

```yaml
sandbox:
  type: my_package.my_module.MyEnvironment
```

The credentials of the remote sandboxes (`SWE_REX_SERVER_URL`,
`SWE_REX_API_KEY`, …) come from the environment or from the `.env` file.

The container works in its own directory, not in the directory of the session:
the path of the host does not exist in a container. Give the container a
directory of its own with the `cwd` option:

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
  cwd: /workspace
```

## The modes of the sandbox

The local sandbox has three modes. They say how much the commands of the agent
may do on the machine of the user, and the **operating system** enforces them:
macOS gets a Seatbelt profile, Linux gets a bubblewrap namespace. A command
that goes too far is stopped by the kernel, not by a rule in a file.

```yaml
sandbox:
  type: local
  mode: workspace-write
```

| `sandbox.mode` | What the commands may do |
|---|---|
| `full-access` | Everything the user may do. The default. |
| `workspace-write` | Read the disk, write inside the working directory |
| `read-only` | Read the disk, write nothing |

The mode is a second axis next to the permission mode. The permissions ask the
user; the sandbox asks nobody. `bypass` skips the questions, it does not open
the disk: the gate and the sandbox are two layers, not a choice.

The `read-only` mode refuses the tools that write files (`write`, `edit`,
`multi_edit`) as well: they write on the machine of the user, outside of the
sandbox. A rule of the user cannot open that either.

The directories the commands may write to are the working directory and the
ones of `permissions.include_dirs`. The temporary directory of the system is
always writable, because a build needs somewhere to put its files.

The network is closed at the operating system too when `permissions.network` is
`deny`: the sandbox has no way out.

A project may close the sandbox, never open it. The tightest of the two modes
wins, so a repository that asks for `read-only` keeps the agent from writing,
whatever the user level says. A project may also not choose **where** the
commands run: the `type` of the sandbox and the options of the environment
(`image` and the rest) are dropped from the configuration of a project, because
an environment of a project would take the workspace of the user with it.

### What the sandbox needs

| System | What it uses |
|---|---|
| macOS | Seatbelt (`sandbox-exec`), it comes with the system |
| Linux | bubblewrap (`bwrap`), it has to be installed |

Without the program the session does not start: the promise cannot be kept, so
it is not made.

The commands of the verification are yours, not the agent's: they run as you,
outside the sandbox.

## What the interface shows

The bar at the top of the interface names the sandbox when it is not the local
one, and `/sandbox` shows the whole configuration:

```
type: swerex_docker
mode: full-access
image: python:3.11
environment: swerex_docker
```

The options that are in effect are listed between the type and the environment.

## The environment has no policy of its own

The remote sandboxes are the environments that came with mini-swe-agent, so
they have no network policy and no list of writable directories. A network policy is a
property of the environment, and it is written there — with the options that the environment
knows. The `docker` sandbox takes the arguments of the `docker` command:

```yaml
sandbox:
  type: docker
  image: python:3.11
  run_args: ["--rm", "--network", "none"]
```

Every sandbox has its own options: the `swerex_docker` one, for instance, takes
`deployment_extra_kwargs` for the deployment of SWE-ReX. The options that the
environment does not know are ignored, so a `run_args` under `swerex_docker`
is dropped without a word.

The paths the agent may touch are a property of the agent, not of the container.
They are bounded by the permission layer: `permissions.deny_paths` for the paths
that are off limits and `permissions.include_dirs` for the ones outside the
directory of the session that are allowed. A denied path is off limits for the
shell as well: `cat .env` is refused when `*.env` is denied. The mode of the
local sandbox tells the same thing to the operating system.

A configuration that still has `sandbox.network` or `sandbox.writable_roots`
keeps working: they are unknown options now, and unknown options are ignored.

## What is still local

The tools that read and write files (`read`, `write`, `edit`, …) work on the
files of the machine of the user, because the sandbox environment only runs
commands. Only the commands of the `bash` tool go into the sandbox.

The `read-only` mode refuses the tools that write as well: they write on the
machine of the user, outside of the sandbox.

The magic of mini-swe-agent brought with it, where a command that prints
`COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` ends the task, is switched off in the
remote sandboxes as well: a turn of the coding agent ends when the model says
so.
