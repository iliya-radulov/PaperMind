from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chapter:
    index: int           # 1-based position inside the book
    title: str
    text: str            # paragraphs separated by blank lines


@dataclass
class Book:
    book_id: str         # stable hash of the file content (not of the name)
    title: str
    author: str
    language: str        # "en", "ru", ...
    source_file: str     # file name only
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    book_id: str
    title: str
    author: str
    language: str
    source_file: str
    chapter_index: int
    chapter_title: str
    chunk_index: int     # position inside the chapter
