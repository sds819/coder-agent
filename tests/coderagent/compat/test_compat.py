"""The code that moved from mini-swe-agent into the coding agent."""

import logging

import pytest

from coderagent.compat import (
    FormatError,
    LocalEnvironment,
    Submitted,
    get_config_from_spec,
    recursive_merge,
    retry,
    set_cache_control,
)
from coderagent.compat.serialize import UNSET


def test_the_later_dictionaries_win():
    """The layers of the configuration are merged: the later one wins."""
    assert recursive_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}
    assert recursive_merge({"a": {"x": 1}}, {"a": {"y": 2}}) == {"a": {"x": 1, "y": 2}}
    assert recursive_merge({"a": {"x": 1}}, {"a": "text"}) == {"a": "text"}


def test_the_unset_values_are_dropped():
    """A layer that says "I don't know" does not overwrite the one that does."""
    assert recursive_merge({"a": 1, "b": UNSET}) == {"a": 1}
    assert recursive_merge({"run": {"task": UNSET}}) == {"run": {}}


def test_the_merged_dictionaries_are_new():
    """The merge does not change the dictionaries it was given."""
    first = {"a": {"x": 1}}
    second = {"a": {"y": 2}}

    recursive_merge(first, second)

    assert first == {"a": {"x": 1}}
    assert second == {"a": {"y": 2}}


def test_a_key_value_is_a_configuration():
    """`model.model_name=x` is a configuration of one key."""
    assert get_config_from_spec("model.model_name=some/model") == {"model": {"model_name": "some/model"}}
    assert get_config_from_spec("agent.max_turns=5") == {"agent": {"max_turns": 5}}
    assert get_config_from_spec("model.temperature=0.5") == {"model": {"temperature": 0.5}}


def test_a_key_value_needs_a_key():
    """An empty key is a mistake of the command line."""
    with pytest.raises(ValueError, match="empty config key"):
        get_config_from_spec("model..name=x")


def test_a_file_is_a_configuration(tmp_path):
    """A file of the user is a configuration."""
    path = tmp_path / "config.yaml"
    path.write_text("model:\n  model_name: some/model\n")

    assert get_config_from_spec(path) == {"model": {"model_name": "some/model"}}


def test_a_file_that_is_not_there_is_an_error(tmp_path):
    """A configuration that cannot be found says so."""
    with pytest.raises(FileNotFoundError):
        get_config_from_spec(tmp_path / "nothing.yaml")


def test_the_cache_control_marks_the_last_message():
    """Only the last message is worth keeping in the cache."""
    messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]

    marked = set_cache_control(messages)

    assert "cache_control" not in marked[0]
    assert marked[1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert messages[1]["content"] == "hi"


def test_the_cache_control_can_be_turned_off():
    """A model that does not cache gets the messages as they are."""
    messages = [{"role": "user", "content": "hello"}]

    assert set_cache_control(messages, mode=None) == messages


def test_the_cache_control_knows_its_modes():
    """Only the mode that mini-swe-agent knows is accepted."""
    with pytest.raises(ValueError, match="Invalid mode"):
        set_cache_control([{"role": "user", "content": "hello"}], mode="ephemeral")


def test_a_command_runs_on_this_machine(tmp_path):
    """The environment of the agent runs the commands of the agent."""
    environment = LocalEnvironment(cwd=str(tmp_path))

    output = environment.execute({"command": "echo hello"})

    assert output["output"].strip() == "hello"
    assert output["returncode"] == 0


def test_the_environment_of_the_commands_can_be_replaced(tmp_path):
    """The commands of the agent do not see the keys of the user."""
    environment = LocalEnvironment(cwd=str(tmp_path))
    environment.env_override = {"PATH": "/usr/bin"}

    assert environment.environment() == {"PATH": "/usr/bin"}


def test_the_sentinel_of_mini_swe_agent_is_still_there(tmp_path):
    """The environment says that the task is done when the command says so."""
    environment = LocalEnvironment(cwd=str(tmp_path))

    with pytest.raises(Submitted):
        environment.execute({"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"})


def test_the_format_error_keeps_its_details():
    """The details of a broken answer are in the messages, not in the text."""
    error = FormatError({"error": "the arguments are not json"})

    assert error.messages == ({"error": "the arguments are not json"},)


def test_the_retry_gives_up_on_the_errors_that_must_not_be_retried():
    """An error that will not get better by waiting is raised at once."""
    calls = []

    def call():
        calls.append(1)
        raise ValueError("no")

    with pytest.raises(ValueError):
        _call_with_retry(call)

    assert len(calls) == 1


def _call_with_retry(call):
    """The call, with the retries of the model calls."""
    for attempt in retry(logger=logging.getLogger("coderagent.test"), abort_exceptions=[ValueError], attempts=2):
        with attempt:
            call()
