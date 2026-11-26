"""The pieces of mini-swe-agent that the coding agent needed.

They were copied here on 2026-11-26, when the coding agent had to stand on its
own without another package next to it. The behaviour is the same as the
original, the names are the same, so that the code that uses them did not have
to change.

The environments are not here: they have a home of their own now,
`coderagent.environments`.
"""

from coderagent.compat.cache_control import set_cache_control
from coderagent.compat.config_spec import get_config_from_spec, get_config_path
from coderagent.compat.exceptions import FormatError, InterruptAgentFlow, Submitted
from coderagent.compat.retry import retry
from coderagent.compat.serialize import recursive_merge

__all__ = [
    "FormatError",
    "InterruptAgentFlow",
    "Submitted",
    "get_config_from_spec",
    "get_config_path",
    "recursive_merge",
    "retry",
    "set_cache_control",
]
