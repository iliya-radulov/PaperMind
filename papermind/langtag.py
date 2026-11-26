"""Tiny script-based language tagging. Enough to tell Cyrillic from Latin text."""
from __future__ import annotations

import re

_CYR = re.compile(r"[Ѐ-ӿ]")
_LAT = re.compile(r"[A-Za-z]")


def detect_language(text: str, hint: str | None = None) -> str:
    """Return a 2-letter code. Cyrillic -> 'ru' (or the hint if it is a Cyrillic language),
    Latin script -> the hint if given, else 'en'."""
    sample = text[:4000]
    cyr = len(_CYR.findall(sample))
    lat = len(_LAT.findall(sample))
    hint = (hint or "").lower().split("-")[0] or None
    if cyr > lat:
        return hint if hint in {"ru", "uk", "bg", "sr", "be"} else "ru"
    return hint if hint and hint not in {"ru", "uk", "bg", "sr", "be"} else "en"
