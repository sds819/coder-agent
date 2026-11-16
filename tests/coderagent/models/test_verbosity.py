"""How much the model says."""

import pytest

from coderagent.config.schema import Config
from coderagent.models.verbosity import VERBOSITIES, note
from coderagent.run import build_loop


def test_every_level_has_a_note():
    assert all(note(level) for level in VERBOSITIES)


def test_no_level_means_no_note():
    """The habit of the model is the habit of the model."""
    assert note("") == ""


def test_a_level_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="unknown verbosity"):
        Config(model={"verbosity": "huge"})


def test_the_note_goes_into_the_system_prompt(tmp_path):
    config = Config(model={"verbosity": "low"})
    loop = build_loop(config, tmp_path)
    assert note("low") in loop.system_prompt


def test_without_a_level_the_prompt_stays_the_same(tmp_path):
    config = Config()
    loop = build_loop(config, tmp_path)
    assert not any(note(level) in loop.system_prompt for level in VERBOSITIES)
