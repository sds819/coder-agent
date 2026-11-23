"""The skills that come with the agent: they are read, and the user may shadow them."""

import subprocess
import sys
import zipfile
from pathlib import Path

from coderagent.skills import PRESETS, load_skills, parse_skill

DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>The first line.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body>
</w:document>
"""

SHEET = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>42</v></c></row>
</sheetData></worksheet>
"""

WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>
"""

RELATIONS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>
"""

STRINGS = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<si><t>name</t></si><si><t>value</t></si><si><t>a</t></si>
</sst>
"""


def _presets() -> list[Path]:
    """Every skill that comes with the agent."""
    return sorted(directory for directory in PRESETS.iterdir() if (directory / "SKILL.md").is_file())


def test_the_agent_comes_with_skills():
    """There are skills in the box."""
    assert [directory.name for directory in _presets()] == [
        "code-review",
        "codebase-onboarding",
        "data-analysis",
        "deep-research",
        "frontend-dev",
        "long-document",
        "office-docx",
        "office-pptx",
        "office-xlsx",
        "writing",
    ]


def test_every_preset_names_itself():
    """A preset says its name and what it is for."""
    for directory in _presets():
        skill = parse_skill(directory / "SKILL.md")
        assert skill is not None
        assert skill.name == directory.name
        assert skill.description
        assert skill.body


def test_the_presets_are_loaded(tmp_path):
    """The presets are among the skills of a session."""
    skills = load_skills(tmp_path, tmp_path / "home")

    assert "deep-research" in skills
    assert skills["deep-research"].directory == PRESETS / "deep-research"


def test_a_skill_of_the_user_shadows_a_preset(tmp_path):
    """A skill of the same name wins over the one of the agent."""
    home = tmp_path / "home"
    (home / "skills" / "writing").mkdir(parents=True)
    (home / "skills" / "writing" / "SKILL.md").write_text(
        "---\nname: writing\ndescription: My own way of writing.\n---\n\nDo it my way.\n"
    )

    skills = load_skills(tmp_path, home)

    assert skills["writing"].description == "My own way of writing."


def test_the_text_of_a_word_file_is_read(tmp_path):
    """The script of the preset reads a Word file without any library."""
    path = tmp_path / "report.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", DOCUMENT)

    done = subprocess.run(
        [sys.executable, str(PRESETS / "office-docx" / "scripts" / "docx_text.py"), str(path)],
        capture_output=True,
        text=True,
    )

    assert done.returncode == 0
    assert done.stdout.splitlines() == ["The first line.", "cell"]


def test_the_sheets_of_an_excel_file_are_read(tmp_path):
    """The script of the preset reads an Excel file without any library."""
    path = tmp_path / "book.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", RELATIONS)
        archive.writestr("xl/sharedStrings.xml", STRINGS)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET)

    done = subprocess.run(
        [sys.executable, str(PRESETS / "office-xlsx" / "scripts" / "xlsx_text.py"), str(path)],
        capture_output=True,
        text=True,
    )

    assert done.returncode == 0
    assert done.stdout.splitlines() == ["# Data", "name\tvalue", "a\t\t42"]
