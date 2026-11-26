"""DjVu reader: extracts the text layer with djvutxt (package djvulibre-bin)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..langtag import detect_language
from ..models import Book
from .common import ReaderError, file_hash, pages_to_chapters, paragraphs_from_page_text


def read_djvu(path: Path) -> Book:
    exe = shutil.which("djvutxt")
    if not exe:
        raise ReaderError(
            f"{path.name}: DjVu needs the 'djvutxt' tool. Install it (Debian/Ubuntu: "
            "sudo apt install djvulibre-bin), or convert the book to epub/pdf first."
        )
    try:
        out = subprocess.run([exe, str(path)], capture_output=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise ReaderError(f"{path.name}: djvutxt timed out") from exc
    if out.returncode != 0:
        raise ReaderError(f"{path.name}: djvutxt failed: {out.stderr.decode(errors='replace')[:200]}")
    pages = [paragraphs_from_page_text(p) for p in out.stdout.decode("utf-8", errors="replace").split("\f")]
    chapters = pages_to_chapters(pages)  # empty when the scan has no text layer -> reported as EMPTY
    sample = "\n".join(c.text[:2000] for c in chapters[:3])
    return Book(
        book_id=file_hash(path),
        title=path.stem,
        author="Unknown",
        language=detect_language(sample),
        source_file=path.name,
        chapters=chapters,
    )
