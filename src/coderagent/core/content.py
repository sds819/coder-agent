"""The content of a message: the text, and the images that go with it.

A message that carries an image has a list of parts instead of a string:
that is the shape the providers expect. `text_of` and `images_of` read that
shape, so the rest of the code does not have to care.
"""

import base64
from pathlib import Path

IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
"""The image types a provider takes, by the suffix of the file."""

MAX_IMAGE_BYTES = 5 * 1024 * 1024
"""How big an image may be. A bigger one is refused instead of being sent."""

TOKENS_PER_PIXEL = 1 / 750
"""What a pixel of an image costs. The estimate only drives decisions."""

MODALITY_PARTS = {
    "image_url": "image",
    "input_audio": "audio",
    "video_url": "video",
}
"""The parts of a message that carry something else than text."""


def text_of(content) -> str:
    """The text of a message, whatever shape its content has."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    return "\n".join(str(part.get("text", "")) for part in content if part.get("type") == "text")


def images_of(content) -> list[str]:
    """The images of a message, as the data urls the providers take."""
    if not content or isinstance(content, str):
        return []
    return [
        str(part["image_url"]["url"])
        for part in content
        if part.get("type") == "image_url" and (part.get("image_url") or {}).get("url")
    ]


def parts(text: str, images: list[str]) -> list[dict]:
    """The parts of a message: the text and the images."""
    result = [{"type": "text", "text": text}] if text else []
    result.extend({"type": "image_url", "image_url": {"url": url}} for url in images)
    return result


def with_text(content, text: str) -> list[dict]:
    """The message with its text replaced. The images stay."""
    if isinstance(content, str):
        return text
    return [{"type": "text", "text": text}, *[part for part in content if part.get("type") != "text"]]


def describe_message(content) -> str:
    """The content of a message, as it is shown to the user."""
    text = text_of(content)
    images = images_of(content)
    if not images:
        return text
    note = f"[{len(images)} image{'s' if len(images) > 1 else ''} attached]"
    return f"{text}\n{note}".strip()


def modalities_of(content) -> set[str]:
    """The kinds of content that are not text in a message."""
    if not content or isinstance(content, str):
        return set()
    return {MODALITY_PARTS[part["type"]] for part in content if part.get("type") in MODALITY_PARTS}


def data_url(path: Path) -> str:
    """The image of a file, as the data url a provider takes."""
    suffix = path.suffix.lower().lstrip(".")
    if suffix not in IMAGE_TYPES:
        raise ValueError(f"{path.name} is not an image a provider takes: {', '.join(IMAGE_TYPES)}")
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"{path.name} is too big: {len(data) // 1024} KB, the limit is {MAX_IMAGE_BYTES // 1024} KB")
    return f"data:{IMAGE_TYPES[suffix]};base64,{base64.b64encode(data).decode('ascii')}"


def image_tokens(content) -> int:
    """What the images of a message cost. An estimate, like the rest of the counting."""
    return sum(max(1, _tokens_of_url(url)) for url in images_of(content))


def _tokens_of_url(url: str) -> int:
    """The tokens of one image, from its size in pixels when that is known."""
    if not url.startswith("data:"):
        return 1
    encoded = url.partition(",")[2]
    size = _size_of(encoded)
    if size:
        return int(size[0] * size[1] * TOKENS_PER_PIXEL)
    return max(1, len(encoded) * 3 // 4 // 1024)


def _size_of(encoded: str) -> tuple[int, int] | None:
    """The size of an image in pixels, read from its header."""
    head = encoded[:128]
    try:
        data = base64.b64decode(head + "=" * (-len(head) % 4))
    except Exception:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    return None


__all__ = [
    "IMAGE_TYPES",
    "MAX_IMAGE_BYTES",
    "data_url",
    "describe_message",
    "image_tokens",
    "images_of",
    "modalities_of",
    "parts",
    "text_of",
    "with_text",
]
