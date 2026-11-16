"""The content of a message: the text and the images that go with it."""

import base64

import pytest

from coderagent.core import content
from coderagent.core.content import data_url, describe_message, image_tokens, images_of, parts, text_of, with_text

ONE_PIXEL_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _png(width: int = 1, height: int = 1) -> bytes:
    """A PNG of the given size. The pixels do not matter, the header does."""
    data = bytearray(base64.b64decode(ONE_PIXEL_PNG))
    data[16:20] = width.to_bytes(4, "big")
    data[20:24] = height.to_bytes(4, "big")
    return bytes(data)


def test_the_text_of_a_message_with_an_image():
    message = parts("what is this?", ["data:image/png;base64,AAAA"])
    assert text_of(message) == "what is this?"
    assert images_of(message) == ["data:image/png;base64,AAAA"]


def test_the_text_of_a_plain_message_is_the_message():
    assert text_of("hello") == "hello"
    assert text_of("") == ""
    assert images_of("hello") == []


def test_a_message_with_only_an_image_has_no_text():
    assert text_of(parts("", ["data:image/png;base64,AAAA"])) == ""
    assert len(parts("", ["data:image/png;base64,AAAA"])) == 1


def test_the_text_of_a_message_can_be_replaced():
    """The text changes, the images stay."""
    message = with_text(parts("old", ["data:image/png;base64,AAAA"]), "new")
    assert text_of(message) == "new"
    assert images_of(message) == ["data:image/png;base64,AAAA"]
    assert with_text("old", "new") == "new"


def test_the_user_sees_that_an_image_is_attached():
    assert describe_message(parts("look", ["data:image/png;base64,AAAA"])) == "look\n[1 image attached]"
    assert describe_message("plain") == "plain"


def test_the_image_of_a_file_becomes_a_data_url(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(_png())
    url = data_url(path)
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.partition(",")[2]) == _png()


def test_a_file_that_is_not_an_image_is_refused(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="not an image"):
        data_url(path)


def test_an_image_that_is_too_big_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "shot.png"
    path.write_bytes(_png())
    monkeypatch.setattr(content, "MAX_IMAGE_BYTES", 10)
    with pytest.raises(ValueError, match="too big"):
        data_url(path)


def test_the_cost_of_an_image_is_estimated_from_its_size(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(_png(1000, 1000))
    assert image_tokens(parts("", [data_url(path)])) == 1333


def test_a_message_without_an_image_costs_nothing():
    assert image_tokens(parts("hello", [])) == 0
    assert image_tokens("hello") == 0
