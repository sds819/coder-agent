"""What a model can take: the pictures, the sound, the video.

A model that cannot see a picture answers anyway, and the answer is made up.
So the agent asks before it sends: the user says what a model takes, and litellm
says it for the models it knows.
"""

from functools import cache

from coderagent.models import litellm_module

MODALITIES = {
    "image": "supports_vision",
    "audio": "supports_audio_input",
    "video": "supports_video_input",
}
"""The kinds of content that are not text, and the key litellm knows them by."""

TAKES = {
    "image": "take pictures",
    "audio": "take sound",
    "video": "take video",
}
"""How to say it in a sentence."""


@cache
def _info(model_name: str) -> dict | None:
    """What litellm knows about a model. None when it does not know it."""
    try:
        return litellm_module().get_model_info(model_name)
    except Exception:
        """A relay station names its models in its own way: litellm does not know them."""
        return None


def support(names: list[str], modality: str, declared: dict | None = None) -> bool | None:
    """Whether the model takes this kind of content.

    `names` are the names of the model: the one the user wrote and the one
    litellm knows. `declared` is what the user said about the models.

    None means: nobody knows. The agent does not send the content then: the
    model would answer about something it cannot see.
    """
    for name in names:
        said = (declared or {}).get(name, {}).get(modality)
        if said is not None:
            return bool(said)
    key = MODALITIES.get(modality)
    if not key:
        return None
    for name in names:
        info = _info(name)
        if info is None:
            continue
        value = info.get(key)
        if value is not None:
            return bool(value)
    return None


__all__ = ["MODALITIES", "TAKES", "support"]
