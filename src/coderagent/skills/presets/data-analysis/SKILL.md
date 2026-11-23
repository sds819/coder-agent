---
name: data-analysis
description: Analyse data (CSV, Excel, JSON, logs) - clean it, compute the figures, draw the charts and state what the data says.
---

# Data analysis

## Steps

1. **Look at the data first.** Print the shape (rows, columns), the head and
   the tail, the missing values and the types. `pandas` when it is
   installed, the `csv` module of the standard library when it is not.
2. **Clean it, and write down what was cleaned.** Rows that are duplicated,
   columns that mix units, dates in two formats, values that are a dash
   instead of a zero. Every decision is a line in the report.
3. **Ask what the question is.** What is being measured, over which period,
   compared with what. When the question is missing, the numbers you find
   are decoration.
4. **Compute.** The figures are simple: totals, shares, changes, rates,
   distributions. Keep the formula next to the number.
5. **Draw.** A chart per finding, not per column: a line for a trend, a bar
   for a comparison, a scatter for a relation. `matplotlib` when it is
   installed; otherwise a Markdown table and a note that the chart needs
   it.
6. **Write it up.** `analysis.md`: the question, the method, the findings
   with their numbers, and the caveats.

## Rules

- The denominator is written next to every rate.
- A correlation is not a cause, and an outlier is not an error until it is
  looked at.
- Never fill a missing value silently: either drop the rows and say how
  many, or fill it and say with what.
- Show the code that produced the number, so the number can be checked.
