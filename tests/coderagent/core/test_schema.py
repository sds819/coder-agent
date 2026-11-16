"""The schema of the answer: the model is asked for JSON, and it has to fit."""

from coderagent.core.events import EventBus
from coderagent.core.loop import AgentLoop
from coderagent.core.schema import note, parse, validate
from coderagent.core.session import SessionStore
from coderagent.models.gateway import ModelGateway
from coderagent.testing.factory import build_context, build_executor
from coderagent.testing.scripted_model import ScriptedModel

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "count": {"type": "integer"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _assistant(content: str = "") -> dict:
    return {"role": "assistant", "content": content, "tool_calls": [], "extra": {"cost": 0.0}}


def _loop(tmp_path, responses, schema=SCHEMA):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    bus = EventBus()
    executor = build_executor(tmp_path, store=store, context=build_context(tmp_path, session=session, bus=bus))
    return AgentLoop(
        ModelGateway(ScriptedModel(responses)),
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
        output_schema=schema,
    )


def test_a_value_that_fits_the_schema_has_no_errors():
    assert validate({"answer": "hi", "count": 2}, SCHEMA) == []


def test_the_wrong_type_is_an_error():
    assert validate({"answer": 3}, SCHEMA) == ["'answer' must be string"]


def test_a_missing_field_is_an_error():
    assert validate({"count": 2}, SCHEMA) == ["the answer is missing 'answer'"]


def test_an_unknown_field_is_an_error():
    assert "the answer has the unknown field 'extra'" in validate({"answer": "hi", "extra": 1}, SCHEMA)


def test_a_boolean_is_not_a_number():
    assert validate({"answer": "hi", "count": True}, SCHEMA) == ["'count' must be integer"]


def test_the_items_of_an_array_are_checked():
    schema = {"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string"}}}}
    assert validate({"tags": ["a", 2]}, schema) == ["'tags[1]' must be string"]


def test_a_value_that_is_not_in_the_enum_is_an_error():
    schema = {"type": "object", "properties": {"answer": {"enum": ["a", "b"]}}}
    assert validate({"answer": "c"}, schema) == ["'answer' must be one of ['a', 'b']"]


def test_a_value_that_may_be_nothing_fits():
    assert (
        validate({"answer": None}, {"type": "object", "properties": {"answer": {"type": "string", "nullable": True}}})
        == []
    )


def test_a_type_that_is_a_list_accepts_every_one_of_them():
    assert validate({"answer": None}, {"type": "object", "properties": {"answer": {"type": ["string", "null"]}}}) == []


def test_the_json_in_a_code_fence_is_read():
    assert parse('```json\n{"answer": "hi"}\n```') == ({"answer": "hi"}, "")


def test_the_json_around_a_sentence_is_read():
    assert parse('Here it is: {"answer": "hi"} - done') == ({"answer": "hi"}, "")


def test_a_text_without_json_is_an_error():
    value, reason = parse("just a sentence")
    assert value is None
    assert "not valid JSON" in reason


def test_the_note_says_what_the_answer_has_to_look_like():
    assert '"answer"' in note(SCHEMA)
    assert "JSON only" in note(SCHEMA)


def test_an_answer_that_fits_the_schema_is_the_output(tmp_path):
    loop = _loop(tmp_path, [_assistant(content='{"answer": "hi", "count": 2}')])
    result = loop.run_turn("do it")
    assert result.stop_reason == "end_turn"
    assert result.output == {"answer": "hi", "count": 2}


def test_an_answer_that_does_not_fit_is_given_back_to_the_model(tmp_path):
    loop = _loop(tmp_path, [_assistant(content="here you go"), _assistant(content='{"answer": "hi"}')])
    result = loop.run_turn("do it")
    assert result.stop_reason == "end_turn"
    assert result.output == {"answer": "hi"}
    assert any("[schema]" in message.get("content", "") for message in result.messages)


def test_an_answer_that_never_fits_ends_the_turn_with_a_reason(tmp_path):
    loop = _loop(tmp_path, [_assistant(content="one"), _assistant(content="two")])
    result = loop.run_turn("do it")
    assert result.stop_reason == "schema_invalid"
    assert "not valid JSON" in result.error
    assert result.output is None


def test_the_model_is_told_about_the_schema(tmp_path):
    loop = _loop(tmp_path, [_assistant(content='{"answer": "hi"}')])
    loop.run_turn("do it")
    assert "<output_schema>" in loop.context.system_prompt


def test_without_a_schema_the_answer_is_not_checked(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create(tmp_path)
    bus = EventBus()
    executor = build_executor(tmp_path, store=store, context=build_context(tmp_path, session=session, bus=bus))
    loop = AgentLoop(
        ModelGateway(ScriptedModel([_assistant(content="just a sentence")])),
        executor,
        session,
        store,
        bus,
        tools=executor.registry.schemas(),
    )
    result = loop.run_turn("do it")
    assert result.stop_reason == "end_turn"
    assert result.output is None
