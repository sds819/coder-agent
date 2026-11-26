"""The environment that runs the commands of the agent on this machine."""


class InterruptAgentFlow(Exception):
    """Raised to interrupt the agent flow and add messages."""

    def __init__(self, *messages: dict):
        self.messages = messages
        super().__init__()


class Submitted(InterruptAgentFlow):
    """Raised when the agent has completed its task."""


class FormatError(InterruptAgentFlow):
    """Raised when the LM's output is not in the expected format.

    The details are in `messages`, not in the text of the exception.
    """
