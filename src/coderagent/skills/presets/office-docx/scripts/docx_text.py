"""The text of a Word file: its paragraphs and its tables."""

import sys
import zipfile
from xml.etree import ElementTree

WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def text_of(node) -> str:
    """The text of a node of the document."""
    return "".join(part.text or "" for part in node.iter(f"{WORD}t"))


def lines_of(archive: zipfile.ZipFile) -> list[str]:
    """The paragraphs and the rows of the tables, in the order of the document."""
    root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{WORD}body")
    lines = []
    for child in body if body is not None else []:
        if child.tag == f"{WORD}p":
            line = text_of(child).strip()
            if line:
                lines.append(line)
        elif child.tag == f"{WORD}tbl":
            for row in child.iter(f"{WORD}tr"):
                cells = [text_of(cell).strip() for cell in row.findall(f"{WORD}tc")]
                lines.append("\t".join(cells))
    return lines


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: docx_text.py FILE.docx")
    with zipfile.ZipFile(sys.argv[1]) as archive:
        print("\n".join(lines_of(archive)))
