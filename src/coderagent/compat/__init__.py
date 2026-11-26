"""The pieces of mini-swe-agent that the coding agent still needs.

They were copied here on 2026-11-26: the coding agent must run on its own, without
another package next to it. The behaviour is the same as the original, the names
are the same, so that the code that uses them does not have to change.

The remote sandboxes are not here: they still come from mini-swe-agent, because
they stand on SWE-ReX, Modal and contree-sdk.
"""

from coderagent.compat.cache_control import set_cache_control
from coderagent.compat.config_spec import get_config_from_spec, get_config_path
from coderagent.compat.environments import LocalEnvironment, LocalEnvironmentConfig, is_local
from coderagent.compat.exceptions import FormatError, InterruptAgentFlow, Submitted
from coderagent.compat.retry import retry
from coderagent.compat.serialize import recursive_merge

__all__ = [
    "FormatError",
    "InterruptAgentFlow",
    "LocalEnvironment",
    "LocalEnvironmentConfig",
    "Submitted",
    "get_config_from_spec",
    "get_config_path",
    "is_local",
    "recursive_merge",
    "retry",
    "set_cache_control",
]
