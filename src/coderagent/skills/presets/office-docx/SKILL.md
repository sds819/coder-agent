---
name: office-docx
description: Write a Word document (.docx) - a report, a letter, the minutes of a meeting - with headings, tables and a table of contents.
---

# Word documents

## Steps

1. **Plan the document.** Write the outline first: the headings and what
   goes under each of them. The outline is what the reader skims, so it has
   to carry the meaning on its own.
2. **Write it.** Use `python-docx` when it is installed
   (`python -c "import docx"`): it makes headings, tables and a table of
   contents straightforward. When it is not, write the text as Markdown and
   convert it with `pandoc FILE.md -o FILE.docx`; when `pandoc` is not there
   either, write Markdown and tell the user that the file is Markdown.
3. **Fill in the parts that matter.**
   - A cover: title, subtitle, date, author.
   - A table of contents for anything longer than two pages.
   - Headings that number themselves (`1`, `1.1`) when the document is
     technical.
   - Tables for comparisons: a row per item, a column per property, the
     units in the header.
4. **Read it back.** Run `scripts/docx_text.py FILE.docx` (the script is in
   the directory of the skill) and read the output. It is what the reader
   gets, so it is what has to be right: no stray placeholders, no empty
   headings, no lost tables.

## Rules

- Short sentences, active voice, no adjective that does not carry
  information.
- Numbers keep their unit and their date.
- A document that says everything says nothing: cut what the reader already
  knows.
