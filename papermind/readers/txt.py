"""Plain-text reader with encoding detection (UTF-8, then Windows-1251 for Russian, then Latin-1)."""
from __future__ import annotations

import re
from pathlib import Path

from ..langtag import detect_language
from ..models import Book
from .common import assemble, file_hash

_HEADING = re.compile(
    r"^\s*(chapter|part|book|prologue|epilogue|глава|часть|книга|пролог|эпилог)\b.{0,60}$",
    re.IGNORECASE,
)
_CYR = re.compile(r"[Ѐ-ӿ]")
_LETTER = re.compile(r"[^\W\d_]")
SECTION_WORDS = 3000  # when a text has no headings, cut it into sections of about this size


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    cp = data.decode("cp1251", errors="replace")
    letters = _LETTER.findall(cp)
    if letters and len(_CYR.findall(cp)) / len(letters) > 0.3:
        return cp
    return data.decode("cp1252", errors="replace")


def _blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n\n" in text:  # paragraphs separated by blank lines, lines wrapped inside
        raw = [" ".join(b.split()) for b in re.split(r"\n\s*\n", text)]
    else:  # one paragraph per line
        raw = [" ".join(line.split()) for line in text.split("\n")]
    return [b for b in raw if b]


def read_txt(path: Path, min_chapter_words: int = 120) -> Book:
    text = decode_text(path.read_bytes())
    sections: list[tuple[str, list[str]]] = []
    title, paras = "", []
    for block in _blocks(text):
        if _HEADING.match(block) and len(block.split()) <= 10:
            if paras:
                sections.append((title, paras))
            title, paras = block, []
        else:
            paras.append(block)
    if paras:
        sections.append((title, paras))

    if len(sections) <= 1:  # no usable headings: cut into numbered parts
        every = sections[0][1] if sections else []
        sections, cur, n = [], [], 0
        for p in every:
            cur.append(p)
            n += len(p.split())
            if n >= SECTION_WORDS:
                sections.append((f"part {len(sections) + 1}", cur))
                cur, n = [], 0
        if cur:
            sections.append((f"part {len(sections) + 1}", cur))

    chapters = assemble(sections, min_chapter_words)
    sample = "\n".join(c.text[:2000] for c in chapters[:3])
    return Book(
        book_id=file_hash(path),
        title=path.stem,
        author="Unknown",
        language=detect_language(sample),
        source_file=path.name,
        chapters=chapters,
    )
