"""The sandbox: the place where the commands of the agent run.

The local sandbox runs the commands on the machine of the user. The other
sandboxes are the ones of mini-swe-agent: a Docker container through SWE-ReX,
Modal, bubblewrap or contree. They are chosen with `sandbox.type` in the
configuration:

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
```

The options that the environment does not know are ignored.

The `sandbox.mode` says how much the commands may do on this machine:
`read-only`, `workspace-write` or `full-access`. The modes are enforced by
the operating system (see `coderagent.core.os_sandbox`), so they hold even
when the permission layer lets everything through.
"""

from importlib import import_module
from pathlib import Path
from typing import Any

from coderagent.compat import is_local
from coderagent.config.schema import ENVIRONMENT_CLASSES, ENVIRONMENT_TYPES, SandboxConfig
from coderagent.core.os_sandbox import FULL_ACCESS
from coderagent.tools.builtin.shell import CodingEnvironment

LOCAL = "local"


def sandbox_class(kind: str) -> type:
    """The class of the environment that the name stands for.

    A dotted path is a way to name any environment: the class of the user.
    """
    path = ENVIRONMENT_CLASSES.get(kind, kind)
    if "." not in path:
        raise ValueError(f"unknown sandbox '{kind}'. Use one of: {', '.join(ENVIRONMENT_TYPES)}.")
    module_name, class_name = path.rsplit(".", 1)
    try:
        return getattr(import_module(module_name), class_name)
    except ImportError as error:
        if kind not in ENVIRONMENT_CLASSES:
            raise
        raise ImportError(
            f"The sandbox '{kind}' needs the packages of the remote sandboxes: pip install 'mini-swe-agent[sandbox]'"
        ) from error


def build_environment(config: SandboxConfig, cwd: Path) -> Any:
    """The environment of the session."""
    if config.type == LOCAL:
        return CodingEnvironment(cwd=str(cwd))
    options = config.model_dump(exclude={"type"})
    kind = options.pop("environment_class", config.type)
    """The way of mini-swe-agent to name an environment."""
    environment = sandbox_class(kind)(**options)
    if is_local(environment):
        """A local environment works in the directory of the session."""
        environment.config.cwd = str(cwd)
    if hasattr(environment, "_check_finished"):
        """A coding agent ends a turn when the model says so, not when a command prints a sentinel."""
        environment._check_finished = lambda output: None
    return environment


def describe(environment: Any, kind: str = "", mode: str = "") -> str:
    """The name of the environment, for the interface."""
    if kind and kind != LOCAL:
        return kind
    if not kind:
        kind = (
            LOCAL if environment is None or isinstance(environment, CodingEnvironment) else type(environment).__name__
        )
    if mode and mode != FULL_ACCESS and kind == LOCAL:
        return f"{LOCAL}/{mode}"
    return kind


__all__ = ["LOCAL", "build_environment", "describe", "sandbox_class"]
