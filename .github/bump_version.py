#!/usr/bin/env python3
"""Bump the version of the coding agent."""

import re
import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parents[1] / "src" / "coderagent" / "version.py"
VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)


def main() -> None:
    text = VERSION_FILE.read_text()
    match = VERSION_RE.search(text)
    if not match:
        print("Error: could not find __version__ in", VERSION_FILE)
        sys.exit(1)

    current = match.group(1)
    print(f"Current version: {current}")

    new = input("New version: ").strip()
    if not new:
        print("No version entered, aborting.")
        sys.exit(1)

    updated = text[: match.start(1)] + new + text[match.end(1) :]
    VERSION_FILE.write_text(updated)
    print(f"Updated {VERSION_FILE.relative_to(Path.cwd())}: {current} -> {new}")

    # Commit the changes
    try:
        subprocess.run(["git", "add", str(VERSION_FILE)], check=True)
        subprocess.run(["git", "commit", "-m", "Bump version"], check=True)
        print("Changes committed with message 'Bump version'")
    except subprocess.CalledProcessError as e:
        print(f"Error committing changes: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
