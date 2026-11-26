"""Names: author normalisation and Chroma-safe shelf names."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_RU = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s",
     "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"],
))


def _ascii(text: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFC", text):
        low = ch.lower()
        if low in _RU:
            t = _RU[low]
            out.append(t.capitalize() if ch != low else t)
        else:
            out.append(ch)
    folded = unicodedata.normalize("NFKD", "".join(out))
    return folded.encode("ascii", "ignore").decode()


def shelf_slug(name: str) -> str:
    """Make a valid Chroma collection name (3-512 chars, letters/digits/._-, alphanumeric ends).
    Case is kept ('Fantasy' stays 'Fantasy'); spaces and odd characters become '-'."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", _ascii(name.strip()))
    slug = re.sub(r"\.{2,}", ".", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")
    if not slug:
        return "shelf-" + hashlib.sha1(name.encode()).hexdigest()[:6]
    if len(slug) < 3:
        slug += "-shelf"
    return slug[:512]


def match_existing_shelf(slug: str, existing: list[str]) -> str:
    """On Linux 'Fantasy' and 'fantasy' are different names. Reuse an existing shelf that differs
    only by letter case instead of silently creating a second, near-identical one."""
    if slug in existing:
        return slug
    for name in existing:
        if name.lower() == slug.lower():
            return name
    return slug


def normalize_author(author: str) -> str:
    """'Pratchett, Terry' -> 'Terry Pratchett'; extra spaces removed. Other forms are left alone."""
    author = " ".join(author.split())
    if author.count(",") == 1 and ";" not in author and "&" not in author:
        last, first = (x.strip() for x in author.split(","))
        if last and first:
            return f"{first} {last}"
    return author or "Unknown"
