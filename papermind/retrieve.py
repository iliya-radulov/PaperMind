"""Retrieval with metadata filters, including a spoiler limit ('read up to chapter N')."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .embeddings import Embedder


@dataclass
class Passage:
    text: str
    title: str
    author: str
    language: str
    source_file: str
    book_id: str
    chapter_index: int
    chapter_title: str
    distance: float

    @property
    def cite(self) -> str:
        return f"{self.title} ({self.author}), ch. {self.chapter_index}: {self.chapter_title}"


def build_where(
    author: str | None = None,
    book_id: str | None = None,
    language: str | None = None,
    max_chapter: int | None = None,
) -> dict[str, Any] | None:
    """max_chapter only makes sense together with book_id (chapter numbers are per book)."""
    if max_chapter is not None and not book_id:
        raise ValueError("max_chapter requires book_id (chapter numbers are per book)")
    conds: list[dict[str, Any]] = []
    if author:
        conds.append({"author": author})
    if book_id:
        conds.append({"book_id": book_id})
    if language:
        conds.append({"language": language})
    if max_chapter is not None:
        conds.append({"chapter_index": {"$lte": int(max_chapter)}})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def retrieve(
    col,
    embedder: Embedder,
    question: str,
    k: int = 6,
    **filters: Any,
) -> list[Passage]:
    where = build_where(**filters)
    res = col.query(
        query_embeddings=embedder.embed([question]),
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    for doc, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append(
            Passage(
                text=doc,
                title=m["title"],
                author=m["author"],
                language=m["language"],
                source_file=m["source_file"],
                book_id=m["book_id"],
                chapter_index=m["chapter_index"],
                chapter_title=m["chapter_title"],
                distance=float(dist),
            )
        )
    return out
