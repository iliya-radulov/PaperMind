"""PDF reader. PDFs have no reliable chapters, so pages are grouped into blocks of N pages."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from ..langtag import detect_language
from ..models import Book
from .common import file_hash, pages_to_chapters, paragraphs_from_page_text

PAGES_PER_SECTION = 10


def read_pdf(path: Path) -> Book:
    reader = PdfReader(str(path))
    info = reader.metadata
    title = (getattr(info, "title", None) or path.stem).strip()
    author = (getattr(info, "author", None) or "Unknown").strip()

    pages = [paragraphs_from_page_text(p.extract_text() or "") for p in reader.pages]
    chapters = pages_to_chapters(pages, PAGES_PER_SECTION)

    sample = "\n".join(c.text[:2000] for c in chapters[:3])
    return Book(
        book_id=file_hash(path),
        title=title,
        author=author,
        language=detect_language(sample),
        source_file=path.name,
        chapters=chapters,
    )
