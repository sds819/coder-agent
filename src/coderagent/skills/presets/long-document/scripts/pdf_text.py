"""The text of a PDF: with `pdftotext` when it is there, with `pypdf` otherwise."""

import shutil
import subprocess
import sys
from pathlib import Path


def with_pdftotext(path: Path) -> str | None:
    """The text of the file, when poppler is installed."""
    if not shutil.which("pdftotext"):
        return None
    done = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


def with_pypdf(path: Path) -> str | None:
    """The text of the file, when the library is installed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def text_of(path: Path) -> str:
    """The text of the file, by whatever means are available."""
    text = with_pdftotext(path) or with_pypdf(path)
    if text is None:
        raise SystemExit(f"no way to read {path}: install poppler (pdftotext) or pypdf")
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: pdf_text.py FILE.pdf")
    print(text_of(Path(sys.argv[1])))
