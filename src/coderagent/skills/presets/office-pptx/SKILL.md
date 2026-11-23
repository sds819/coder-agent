---
name: office-pptx
description: Build a slide deck (.pptx) out of an outline - one message per slide, speaker notes under every slide, and a title that says the message.
---

# Slide decks

A deck is not a document cut into pieces. It is a sequence of messages, and
the audience sees all of them at once.

## Steps

1. **Write the spine.** One sentence per slide, in order, before any
   layout. If the spine does not read as a story, the deck is not ready.
2. **Build the slides.** Use `python-pptx` when it is installed
   (`python -c "import pptx"`). Otherwise write the deck as Markdown with
   `---` between the slides and convert it with
   `pandoc slides.md -o slides.pptx`; when that is not there either, hand
   over the Markdown and say what it is.
3. **One message per slide.** A title that states the message ("Costs grew
   40% in Q3"), not the topic ("Costs").
4. **Notes.** Every slide gets speaker notes: what to say, in two or three
   sentences, and what to skip when the time is short.
5. **Check.** Read the slides back and ask: does the title alone tell the
   story? Does any slide hold two messages?

## Rules

- Six to ten words on a slide, twelve at the very most.
- A chart beats a table of numbers; a table beats a paragraph of numbers.
- The deck ends with the decision that was asked for, not with a summary of
  what was just said.
