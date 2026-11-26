"""Paragraph-aware chunking inside chapters, with a small overlap between chunks."""
from __future__ import annotations

import re

from .models import Book, Chunk

_SENT = re.compile(r"(?<=[.!?…»”])\s+")


def _split_long(paragraph: str, max_words: int) -> list[str]:
    """Split a paragraph that is longer than max_words at sentence boundaries."""
    if len(paragraph.split()) <= max_words:
        return [paragraph]
    parts, cur, n = [], [], 0
    for sent in _SENT.split(paragraph):
        w = len(sent.split())
        if cur and n + w > max_words:
            parts.append(" ".join(cur))
            cur, n = [], 0
        cur.append(sent)
        n += w
    if cur:
        parts.append(" ".join(cur))
    # a single sentence longer than max_words: hard split on words
    out = []
    for p in parts:
        words = p.split()
        for i in range(0, len(words), max_words):
            out.append(" ".join(words[i : i + max_words]))
    return out


def chunk_text(text: str, target_words: int = 280, overlap_words: int = 40) -> list[str]:
    paras: list[str] = []
    for p in text.split("\n\n"):
        p = p.strip()
        if p:
            paras.extend(_split_long(p, target_words))

    chunks: list[str] = []
    cur: list[str] = []
    n = 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > target_words:
            chunks.append("\n\n".join(cur))
            # carry the tail of the previous chunk over as overlap
            tail: list[str] = []
            tn = 0
            for prev in reversed(cur):
                pw = len(prev.split())
                if tn + pw > overlap_words and tail:
                    break
                tail.insert(0, prev)
                tn += pw
                if tn >= overlap_words:
                    break
            cur, n = (tail if tn <= overlap_words * 2 else []), (tn if tn <= overlap_words * 2 else 0)
        cur.append(p)
        n += w
    if cur and (not chunks or "\n\n".join(cur) != chunks[-1]):
        chunks.append("\n\n".join(cur))
    return chunks


def chunk_book(book: Book, target_words: int = 280, overlap_words: int = 40) -> list[Chunk]:
    out: list[Chunk] = []
    for ch in book.chapters:
        for i, text in enumerate(chunk_text(ch.text, target_words, overlap_words)):
            out.append(
                Chunk(
                    # hash-based IDs: no collisions between books with similar file names
                    chunk_id=f"{book.book_id}-{ch.index:04d}-{i:04d}",
                    text=text,
                    book_id=book.book_id,
                    title=book.title,
                    author=book.author,
                    language=book.language,
                    source_file=book.source_file,
                    chapter_index=ch.index,
                    chapter_title=ch.title,
                    chunk_index=i,
                )
            )
    return out
