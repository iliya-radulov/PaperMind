"""Author personas for the 'in the author's voice' mode."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FILE = Path(__file__).with_name("personas.default.toml")


@dataclass
class Persona:
    name: str
    match: list[str]
    style: str


def _read(path: Path) -> list[Persona]:
    if not path.is_file():
        return []
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return [
        Persona(p["name"], [m.lower() for m in p.get("match", [])], p.get("style", ""))
        for p in data.get("persona", [])
    ]


def load_personas(user_file: str | Path = "personas.toml") -> list[Persona]:
    merged = {p.name: p for p in _read(DEFAULT_FILE)}
    merged.update({p.name: p for p in _read(Path(user_file))})
    return list(merged.values())


def find_persona(author: str, personas: list[Persona] | None = None) -> Persona:
    """Persona for an author as written in the book metadata; a generic one if none matches."""
    author_l = author.lower()
    for p in personas if personas is not None else load_personas():
        if any(m in author_l for m in p.match):
            return p
    return Persona(
        name=author,
        match=[],
        style="Use the diction, rhythm, humour and typical imagery found in the passages.",
    )
