---
name: codebase-onboarding
description: Get to know an unfamiliar codebase - its layout, its entry points, its build and its tests - and write the map down.
---

# Reading a codebase

## Steps

1. **Look around.** The top-level files say what the project is:
   `README`, `pyproject.toml` or `package.json`, the directory of the
   tests, the directory of the source. Read them.
2. **Find the entry points.** The command that starts it, the module that
   runs it, the place where the requests or the jobs come in. Two or three
   files, not twenty.
3. **Follow one path through.** Take a small thing the project does and
   follow it from the entry point to where it ends: the call, the class, the
   file it writes. That one path explains more than a directory tree.
4. **Find the seams.** Where does the code talk to the outside world (the
   network, the disk, the clock)? Those are the places to look at twice.
5. **Find the tests.** How they are run, what they cover, what they do not.
6. **Write the map.** `CODEBASE.md`: what the project does, the layout, the
   entry points, the path you followed, the build and the test commands, and
   the open questions.

## Rules

- Read before you judge. A file that looks wrong is often doing something
  the name does not say.
- Prefer the names the project itself uses: the terms of the README and of
  the code, not your own.
- The map is for a reader who knows nothing about the project. That is the
  test of every line.
