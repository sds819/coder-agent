"""What a model can take: the pictures, the sound, the video.

A model that cannot see a picture answers anyway, and the answer is made up.
So the agent asks before it sends: the user says what a model takes, litellm
says it for the models it knows, and the agent tries it out for the models
nobody knows about.
"""

import base64
import struct
import zlib
from collections.abc import Callable
from functools import cache

from coderagent.core.content import parts
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

PROBE_QUESTION = "What color is this picture? Answer with one word."
"""The question the probe asks. The answer of a model that sees is short."""

PROBE_PICTURES = {
    "image": ((255, 0, 255), ("magenta", "purple", "pink", "fuchsia", "violet")),
}
"""The color of the picture of the probe, and the words that name it.

A color nobody guesses by accident: a model that cannot see the picture has
nothing to say about it.
"""

PROBE_TRIES = 2
"""How many times the probe asks. A relay station answers nothing now and then."""


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


def _png(rgb: tuple[int, int, int], size: int = 32) -> bytes:
    """A picture of one solid color, as a PNG. It is built here: the probe needs no file."""
    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def probe_picture(modality: str) -> str:
    """The picture of the probe, as the data url a provider takes."""
    rgb, _ = PROBE_PICTURES[modality]
    return "data:image/png;base64," + base64.b64encode(_png(rgb)).decode("ascii")


def probe(query: Callable[[list[dict]], str], modality: str) -> bool | None:
    """Whether the model takes this kind of content: it is asked about a picture.

    `query` sends the messages and returns the answer of the model. True when the
    answer names the color of the picture, False when the answer says something
    else, None when nobody knows: the model did not answer, or it does not take
    this kind of content at all.
    """
    if modality not in PROBE_PICTURES:
        """Only a picture can be asked about. The sound and the video cannot."""
        return None
    _, words = PROBE_PICTURES[modality]
    url = probe_picture(modality)
    for _ in range(PROBE_TRIES):
        try:
            answer = query([{"role": "user", "content": parts(PROBE_QUESTION, [url])}])
        except Exception as error:
            text = str(error).lower()
            if any(word in text for word in ("image", "vision", "picture", "multimodal")):
                """The provider says it does not take pictures. That is an answer."""
                return False
            return None
        said = str(answer or "").strip().lower()
        if not said:
            """The relay station answers nothing now and then. It is asked again."""
            continue
        return any(word in said for word in words)
    return None


__all__ = ["MODALITIES", "PROBE_QUESTION", "TAKES", "probe", "probe_picture", "support"]
