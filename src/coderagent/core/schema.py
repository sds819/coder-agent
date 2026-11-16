"""The shape the answer of the agent has to have.

The model is asked for JSON that fits a schema, and the answer is checked
against it here. The schema is a small part of JSON Schema: the keywords that
say what a value is and what it holds. That is on purpose: the repository does
not carry a validator, and a schema that nobody checks is a schema that lies.
"""

import json
from typing import Any

TYPES = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}
"""How a value of each type is recognized. A boolean is not a number."""


def validate(value: Any, schema: dict, where: str = "") -> list[str]:
    """The ways the value does not fit the schema. An empty list means it fits."""
    if not isinstance(schema, dict):
        return []
    errors = []
    if value is None and schema.get("nullable"):
        """A value that may be nothing fits, whatever its type says."""
        return []
    label = f"'{where}'" if where else "the answer"
    expected = schema.get("type")
    if expected:
        names = expected if isinstance(expected, list) else [expected]
        if not any(TYPES.get(name, lambda _value: True)(value) for name in names):
            return [f"{label} must be {' or '.join(str(name) for name in names)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{label} must be one of {schema['enum']}")
    if isinstance(value, dict):
        errors.extend(_object_errors(value, schema, where))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(validate(item, schema["items"], f"{where}[{index}]"))
    return errors


def _object_errors(value: dict, schema: dict, where: str) -> list[str]:
    """The ways the object does not fit the schema."""
    errors = []
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    for name in schema.get("required") or []:
        if name not in value:
            errors.append(f"{where or 'the answer'} is missing '{name}'")
    for name, item in value.items():
        if name in properties:
            errors.extend(validate(item, properties[name], f"{where}.{name}" if where else name))
        elif schema.get("additionalProperties") is False:
            errors.append(f"{where or 'the answer'} has the unknown field '{name}'")
    return errors


def parse(text: str) -> tuple[Any, str]:
    """The JSON in the text, and the reason when there is none.

    The answer of a model is often wrapped in a code fence, and sometimes it
    has a sentence in front of it. Both are read.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        stripped = "\n".join(lines).strip().removesuffix("```").strip()
    try:
        return json.loads(stripped), ""
    except json.JSONDecodeError:
        """The text is not JSON on its own. There may be an object in it."""
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        """There is an object in there: the text around it does not matter."""
        try:
            return json.loads(stripped[start : end + 1]), ""
        except json.JSONDecodeError as error:
            return None, _reason(error)
    return None, _reason(None)


def _reason(error: json.JSONDecodeError | None) -> str:
    """Why the answer is not JSON."""
    if error is None:
        return "the answer is not valid JSON: there is no JSON in it"
    return f"the answer is not valid JSON: {error.msg} (line {error.lineno}, column {error.colno})"


def note(schema: dict) -> str:
    """What the model is told about the schema it has to fit."""
    return (
        "<output_schema>\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
        "</output_schema>\n"
        "Your answer must be JSON that fits this schema. "
        "Answer with the JSON only: no prose, no explanation, no code fences."
    )


__all__ = ["TYPES", "note", "parse", "validate"]
