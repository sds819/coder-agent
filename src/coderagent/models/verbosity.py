"""How much the model says. Provider agnostic: it is an instruction, not a parameter."""

VERBOSITIES = ("low", "medium", "high")

NOTES = {
    "low": "Answer briefly: the result and what changed, without the reasoning behind it.",
    "medium": "Answer with the result and the reasoning that matters, without padding.",
    "high": "Answer in detail: the result, the reasoning, and the caveats.",
}


def note(level: str) -> str:
    """The line that goes into the system prompt. Empty for the habit of the model."""
    return NOTES.get(level, "")
