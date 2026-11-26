"""Pieces shared by all readers."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..models import Chapter


class ReaderError(Exception):
    """A problem the user can fix (missing tool, unsupported file). The message says how."""


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def assemble(sections: list[tuple[str, list[str]]], min_chapter_words: int) -> list[Chapter]:
    """Turn (heading, paragraphs) sections into chapters. A section shorter than
    min_chapter_words (title page, dedication, a one-line epigraph) is folded into the next one."""
    chapters: list[Chapter] = []
    title, paras, words = "", [], 0

    def flush(force: bool = False) -> None:
        nonlocal title, paras, words
        if paras and (words >= min_chapter_words or force):
            chapters.append(
                Chapter(len(chapters) + 1, title or f"Chapter {len(chapters) + 1}", "\n\n".join(paras))
            )
            title, paras, words = "", [], 0

    for heading, ps in sections:
        if words >= min_chapter_words:
            flush()
        if not title:
            title = heading
        elif heading:
            paras.append(heading)
        paras.extend(ps)
        words += sum(len(p.split()) for p in ps)
    flush(force=True)  # whatever is left belongs to the last chapter
    return chapters


def pages_to_chapters(pages: list[list[str]], per_section: int = 10) -> list[Chapter]:
    """For formats without chapters (PDF, DjVu): group pages into numbered sections."""
    chapters: list[Chapter] = []
    for start in range(0, len(pages), per_section):
        end = min(start + per_section, len(pages))
        paras = [p for page in pages[start:end] for p in page]
        if paras:
            chapters.append(Chapter(len(chapters) + 1, f"pages {start + 1}-{end}", "\n\n".join(paras)))
    return chapters


def paragraphs_from_page_text(page_text: str) -> list[str]:
    """Page text breaks lines inside paragraphs: join the lines, split on blank lines."""
    out = []
    for block in page_text.replace("\r", "").split("\n\n"):
        block = " ".join(block.split())
        if block:
            out.append(block)
    return out
