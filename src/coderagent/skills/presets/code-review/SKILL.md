---
name: code-review
description: Review a change before it is committed - correctness first, then the tests, then the shape of the code and its docs.
---

# Code review

A review that lists style nits is noise. A review that misses a bug is
worse. The order below is the order of importance.

## Steps

1. **Read the change as a whole.** `git diff` first, then the files around
   it. A diff without its context hides the bug.
2. **Correctness.** For each change ask: what input breaks it? What happens
   when the value is empty, zero, huge or missing? Is the error handled
   where it can be? Is the state shared between two callers that assume
   they own it?
3. **The tests.** Is there a test for the behaviour that changed? Does it
   fail without the change? Do the tests that exist still pass? Run them.
4. **The shape.** Names that say what the thing is, functions that do one
   thing, no dead code, no duplication that has to be kept in step.
5. **The edges.** Security (injection, secrets in the code, paths from the
   outside), performance (a loop inside a loop, a query in a loop), the
   compatibility of the interface.
6. **Write the review.** Every point has a file, a line, what is wrong and
   what to do about it. Mark the blocking points as such. Say plainly when
   the change is good: a review that only lists faults teaches nothing.

## Rules

- One issue per point, with the line that holds it.
- Say what is wrong before saying how to fix it.
- Do not rewrite the code in the review; the author decides.
- A question is not a fault: mark it as a question.
