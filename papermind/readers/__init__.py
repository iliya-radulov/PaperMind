from __future__ import annotations

from pathlib import Path

from ..models import Book

SUPPORTED = {".epub", ".pdf"}


def read_book(path: str | Path, min_chapter_words: int = 120) -> Book:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".epub":
        from .epub import read_epub
        return read_epub(path, min_chapter_words)
    if suffix == ".pdf":
        from .pdf import read_pdf
        return read_pdf(path)
    raise ValueError(f"Unsupported file type: {path.name} (supported: epub, pdf)")
