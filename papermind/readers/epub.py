"""EPUB reader that keeps the chapter structure (needed for citations and spoiler limits)."""
from __future__ import annotations

import hashlib
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import ITEM_DOCUMENT, epub

from ..langtag import detect_language
from ..models import Book, Chapter

_BLOCKS = ("p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6")
_SPLIT_HEADINGS = ("h1", "h2")


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def _meta(book: epub.EpubBook, key: str) -> str:
    values = book.get_metadata("DC", key)
    return values[0][0].strip() if values and values[0] and values[0][0] else ""


def _sections(html: bytes) -> list[tuple[str, list[str]]]:
    """Split one HTML document into (heading, paragraphs) sections at h1/h2."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    sections: list[tuple[str, list[str]]] = []
    title, paras = "", []
    for el in body.find_all(_BLOCKS):
        # skip containers: only take leaf-most blocks to avoid duplicated text
        if el.name in ("div", "blockquote", "li") and el.find(_BLOCKS):
            continue
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name in _SPLIT_HEADINGS:
            if paras:
                sections.append((title, paras))
            title, paras = text, []
        else:
            paras.append(text)
    if paras:
        sections.append((title, paras))
    return sections


def read_epub(path: Path, min_chapter_words: int = 120) -> Book:
    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    title = _meta(book, "title") or path.stem
    author = _meta(book, "creator") or "Unknown"

    chapters: list[Chapter] = []
    pending_title, pending_paras, pending_words = "", [], 0

    def flush(force: bool = False) -> None:
        nonlocal pending_title, pending_paras, pending_words
        if pending_paras and (pending_words >= min_chapter_words or force):
            chapters.append(
                Chapter(
                    index=len(chapters) + 1,
                    title=pending_title or f"Chapter {len(chapters) + 1}",
                    text="\n\n".join(pending_paras),
                )
            )
            pending_title, pending_paras, pending_words = "", [], 0

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        for heading, paras in _sections(item.get_content()):
            # a heading starts a new chapter only if what we hold is already long enough
            if pending_words >= min_chapter_words:
                flush()
            if not pending_title:
                pending_title = heading
            elif heading:
                pending_paras.append(heading)
            pending_paras.extend(paras)
            pending_words += sum(len(p.split()) for p in paras)
    flush(force=True)  # whatever is left at the end belongs to the last chapter

    sample = "\n".join(c.text[:2000] for c in chapters[:3])
    language = detect_language(sample, _meta(book, "language"))
    return Book(
        book_id=file_hash(path),
        title=title,
        author=author,
        language=language,
        source_file=path.name,
        chapters=chapters,
    )
