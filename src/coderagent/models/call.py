"""The parameters of a call to a model: the ones that belong to the agent."""

from typing import Any

RESERVED = ("model", "messages", "tools", "stream", "stream_options")
"""The parameters of the call that the agent sets itself.

The model and the messages are the ones of the agent, the tools are the ones
of the session, and the stream is how the answer arrives. A user who sets one
of them breaks the call in a way that only shows at runtime.
"""


def check_reserved(kwargs: dict[str, Any]) -> None:
    """Refuse the parameters that the agent sets itself."""
    for key in RESERVED:
        if key in kwargs:
            raise ValueError(f"'model_kwargs' must not have '{key}': the agent sets it itself.")
