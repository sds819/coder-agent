---
name: long-document
description: Read a long document (PDF, Word file, paper, contract, report) and answer questions about it with quotes and page numbers.
---

# Long documents

A long document is read, not skimmed. The text is extracted first, then
structured, then answered.

## Steps

1. **Find the text.** For a PDF run `scripts/pdf_text.py FILE.pdf` (the script
   is in the directory of the skill): it uses `pdftotext` when it is installed
   and `pypdf` otherwise. For a Word file use the script of the `office-docx`
   skill, `docx_text.py`. Keep the extracted text in `work/` next to the
   original.
2. **Outline it.** Write down the structure of the document: the headings,
   the tables, the appendices. A document that is scanned images has no
   text: say so and ask for a text version instead of guessing.
3. **Answer.** Every answer quotes the sentence it rests on and names where
   it is (page, section or heading). Numbers keep the unit and the date of
   the document.
4. **Check the tables.** A table is read as a table: read the header row and
   the units first, then the rows. Do not average a column that holds
   categories.
5. **Report.** Give the answer first, then the evidence, then what the
   document does not say.

## Rules

- The document is the truth here, not your own knowledge. When they differ,
  the document wins and the difference is written down.
- Never cite a page you did not read. When the text has no page numbers,
  cite the heading.
- Long documents are read in parts: read the whole text once for the shape,
  then read closely the parts the question needs.
