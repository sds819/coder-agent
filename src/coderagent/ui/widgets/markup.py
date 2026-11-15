"""Text that comes from the model, as markup the interface can show."""


def literal(text: str) -> str:
    """Escape a text, so that Textual does not read it as markup.

    `textual.markup.escape` only escapes the tags of Rich; Textual reads every
    `[` as the start of a tag, so the brackets are escaped by hand.
    """
    return text.replace("[", "\\[")
