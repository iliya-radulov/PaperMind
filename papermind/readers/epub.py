"""EPUB reader that keeps the chapter structure (needed for citations and spoiler limits)."""
from __future__ import annotations

import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import ITEM_DOCUMENT, epub

from ..langtag import detect_language
from ..models import Book
from .common import assemble, file_hash  # noqa: F401  (file_hash re-exported for older imports)

_BLOCKS = ("p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6")
_SPLIT_HEADINGS = ("h1", "h2")


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

    sections: list[tuple[str, list[str]]] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        sections.extend(_sections(item.get_content()))
    chapters = assemble(sections, min_chapter_words)

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
