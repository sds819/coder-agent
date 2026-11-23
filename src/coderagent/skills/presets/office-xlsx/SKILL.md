---
name: office-xlsx
description: Read and write Excel workbooks - formulas, tables and summaries of many rows. Also handles CSV and TSV.
---

# Spreadsheets

## Steps

1. **Look before writing.** Run `scripts/xlsx_text.py FILE.xlsx` (the script is
   in the directory of the skill) to see the sheets, the columns and the
   types. For a CSV, read the first rows and the header line with the `read`
   tool.
2. **Learn the shape.** Name the columns you will use and the unit of each
   of them. A column of dates is not a column of strings, and a percentage
   is not a number between 0 and 1 without saying so.
3. **Compute in the workbook.** Put the formula in the cell, not the value:
   `=SUM(C2:C500)`, `=AVERAGEIF(...)`, `=VLOOKUP(...)`. Use
   `openpyxl` when it is installed; otherwise write the CSV that goes with
   the workbook and say so.
4. **Summarize.** A sheet of results ends with a small table: the figure,
   the period it covers, and how it was computed. Say which rows were left
   out and why.
5. **Check.** Read the workbook back with the script and confirm the totals
   and the formulas are there.

## Rules

- Never overwrite a workbook with a guess: work on a copy and say which
  copy.
- Formulas over values, so the reader can follow the number.
- One table per sheet. A second table on the same sheet is a second sheet.
- The units, the currency and the time zone are written in the header or
  next to the number.
