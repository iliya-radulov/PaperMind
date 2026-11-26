"""FictionBook (FB2) reader, also for .fb2.zip / .fbz archives. Keeps chapter structure."""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from ..langtag import detect_language
from ..models import Book
from .common import ReaderError, assemble, file_hash


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _first(root, name: str):
    found = root.xpath(f".//*[local-name()='{name}']")
    return found[0] if found else None


def _load(path: Path) -> bytes:
    if path.suffix.lower() in (".zip", ".fbz"):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".fb2")]
            if not names:
                raise ReaderError(f"{path.name}: no .fb2 file inside the archive")
            return zf.read(names[0])
    return path.read_bytes()


def _walk(section, out: list[tuple[str, list[str]]]) -> None:
    """Collect (title, paragraphs) for every leaf section; text that sits directly in a
    section that also has subsections becomes its own small section (it gets folded later)."""
    title_el = next((c for c in section if _local(c) == "title"), None)
    title = _text(title_el) if title_el is not None else ""
    children = [c for c in section if _local(c) == "section"]
    paras: list[str] = []
    for child in section:
        if _local(child) in ("title", "section", "image", "annotation"):
            continue
        for el in child.iter():
            if _local(el) in ("p", "v"):
                t = _text(el)
                if t:
                    paras.append(t)
    if paras or not children:
        out.append((title, paras))
    for c in children:
        _walk(c, out)


def read_fb2(path: Path, min_chapter_words: int = 120) -> Book:
    data = _load(path)
    parser = etree.XMLParser(recover=True, huge_tree=True)  # old FB2 files are often not valid XML
    root = etree.fromstring(data, parser=parser)
    if root is None:
        raise ReaderError(f"{path.name}: not a readable FB2 file")

    info = _first(root, "title-info")
    title = author = lang = ""
    if info is not None:
        t = _first(info, "book-title")
        title = _text(t) if t is not None else ""
        a = _first(info, "author")
        if a is not None:
            parts = [_text(x) for n in ("first-name", "middle-name", "last-name") for x in a.xpath(f"./*[local-name()='{n}']")]
            author = " ".join(p for p in parts if p) or (_text(_first(a, "nickname")) if _first(a, "nickname") is not None else "")
        lg = _first(info, "lang")
        lang = _text(lg) if lg is not None else ""

    bodies = root.xpath("/*/*[local-name()='body']")
    main = [b for b in bodies if b.get("name") not in ("notes", "comments")] or bodies
    sections: list[tuple[str, list[str]]] = []
    for body in main:
        top = [c for c in body if _local(c) == "section"]
        if top:
            for s in top:
                _walk(s, sections)
        else:  # body with bare paragraphs
            _walk(body, sections)
    chapters = assemble(sections, min_chapter_words)

    sample = "\n".join(c.text[:2000] for c in chapters[:3])
    return Book(
        book_id=file_hash(path),
        title=title or path.stem,
        author=author or "Unknown",
        language=detect_language(sample, lang),
        source_file=path.name,
        chapters=chapters,
    )
