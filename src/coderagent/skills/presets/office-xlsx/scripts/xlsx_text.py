"""The sheets of an Excel file, as text: the name of the sheet, then its rows."""

import sys
import zipfile
from xml.etree import ElementTree

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOCUMENT = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """The strings of the file: the cells that hold one point at them."""
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(part.text or "" for part in item.iter(f"{MAIN}t")) for item in root.findall(f"{MAIN}si")]


def column_of(reference: str) -> int:
    """The number of the column a cell sits in, from its name."""
    index = 0
    for letter in "".join(character for character in reference if character.isalpha()):
        index = index * 26 + ord(letter.upper()) - 64
    return index - 1


def text_of(cell, shared: list[str]) -> str:
    """The text of a cell."""
    if cell.get("t") == "s":
        return shared[int(cell.findtext(f"{MAIN}v", default="0"))]
    if cell.get("t") == "inlineStr":
        return "".join(part.text or "" for part in cell.iter(f"{MAIN}t"))
    return cell.findtext(f"{MAIN}v", default="")


def sheets_of(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """The name of every sheet and the file that holds it."""
    book = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.get("Id"): item.get("Target", "") for item in relations.findall(f"{PACKAGE}Relationship")}
    sheets = []
    for sheet in book.iter(f"{MAIN}sheet"):
        target = targets.get(sheet.get(f"{DOCUMENT}id"), "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        sheets.append((sheet.get("name", ""), path))
    return sheets


def rows_of(archive: zipfile.ZipFile, path: str, shared: list[str]) -> list[str]:
    """The rows of a sheet, one per line, the cells separated by tabs."""
    root = ElementTree.fromstring(archive.read(path))
    lines = []
    for row in root.iter(f"{MAIN}row"):
        cells: list[str] = []
        for cell in row.findall(f"{MAIN}c"):
            text = text_of(cell, shared).replace("\t", " ").replace("\n", " ")
            while len(cells) < column_of(cell.get("r", "")):
                cells.append("")
            cells.append(text)
        lines.append("\t".join(cells).rstrip("\t"))
    return lines


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: xlsx_text.py FILE.xlsx")
    with zipfile.ZipFile(sys.argv[1]) as archive:
        shared = shared_strings(archive)
        for name, path in sheets_of(archive):
            print(f"# {name}")
            print("\n".join(rows_of(archive, path, shared)))
