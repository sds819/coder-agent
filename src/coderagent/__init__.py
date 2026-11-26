"""The coding agent: a coding agent for the terminal, for the browser and as a library.

See `docs/design/coding-agent-architecture.md` for the architecture this package implements.
"""

import os

# mini-swe-agent greets the user on import when it is installed next to us;
# the coder CLI has its own output.
os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")

# litellm fetches the price table from GitHub while it is imported: seconds of waiting,
# and a failure behind a firewall. The copy it ships with is good enough.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")

from coderagent.core.protocols import ModelBackend, ToolExecutor  # noqa: E402
from coderagent.paths import load_global_env  # noqa: E402
from coderagent.version import __version__  # noqa: E402

load_global_env()
"""The keys of the models come from the files of the user: they have to be in
the environment before the first call to a model."""

__all__ = ["ModelBackend", "ToolExecutor", "__version__"]
