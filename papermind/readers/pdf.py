"""PDF reader. PDFs have no reliable chapters, so pages are grouped into blocks of N pages."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from ..langtag import detect_language
from ..models import Book, Chapter
from .epub import file_hash

PAGES_PER_SECTION = 10


def _paragraphs(page_text: str) -> list[str]:
    # PDF text breaks lines inside paragraphs; join lines, split on blank lines
    out = []
    for block in page_text.replace("\r", "").split("\n\n"):
        block = " ".join(block.split())
        if block:
            out.append(block)
    return out


def read_pdf(path: Path) -> Book:
    reader = PdfReader(str(path))
    info = reader.metadata
    title = (getattr(info, "title", None) or path.stem).strip()
    author = (getattr(info, "author", None) or "Unknown").strip()

    chapters: list[Chapter] = []
    n_pages = len(reader.pages)
    for start in range(0, n_pages, PAGES_PER_SECTION):
        end = min(start + PAGES_PER_SECTION, n_pages)
        paras: list[str] = []
        for i in range(start, end):
            paras.extend(_paragraphs(reader.pages[i].extract_text() or ""))
        if paras:
            chapters.append(
                Chapter(len(chapters) + 1, f"pages {start + 1}-{end}", "\n\n".join(paras))
            )

    sample = "\n".join(c.text[:2000] for c in chapters[:3])
    return Book(
        book_id=file_hash(path),
        title=title,
        author=author,
        language=detect_language(sample),
        source_file=path.name,
        chapters=chapters,
    )
