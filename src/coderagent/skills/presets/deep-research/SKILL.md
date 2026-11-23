---
name: deep-research
description: Look a question up and write a report that carries its sources. Use it when the answer has to be found, compared or cited.
---

# Deep research

A report nobody can check is a guess with a table of contents. Every claim
carries the source it came from, and every source is reachable.

## Steps

1. **Fix the question.** Write it in one sentence, then list the
   sub-questions that have to be answered for it. Ask the user when the
   question is ambiguous in a way that changes the answer.
2. **Search.** Search the web for each sub-question, from the most specific
   wording to the most general. Keep every page worth reading in
   `research/` as markdown: the title, the URL, the date, the text.
3. **Read.** Read the sources themselves, not the summaries of them. The
   paper, the filing and the documentation beat the article about them.
4. **Cross-check.** Every number that matters must show up in two sources
   that do not know each other. Where they disagree, the report says so.
5. **Write** `research/report.md`:
   - the answer in the first paragraph, in three sentences;
   - one section per finding;
   - a table at the end: claim, source, URL, date.
6. **Check.** Open every URL of the table and confirm it says what the report
   claims it says.

## Rules

- Never invent a URL, a title, a date or a number. What cannot be found is
  written as "not found".
- A claim without a source is an assumption: say so, in those words.
- Quote the sentence that carries the claim, with its location, when the
  wording matters.
- Prefer a table over a paragraph when there are more than three things to
  compare.
