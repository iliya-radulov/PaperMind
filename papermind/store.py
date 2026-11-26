"""Chroma wrapper. One Chroma collection per shelf (e.g. 'fantasy', 'scifi')."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

import chromadb

from .embeddings import Embedder
from .models import Chunk


class ShelfNotFound(Exception):
    pass


class Store:
    def __init__(self, path: str):
        self.client = chromadb.PersistentClient(path=path)

    # -- shelves ---------------------------------------------------------
    def list_shelves(self) -> list[str]:
        return sorted(c.name if hasattr(c, "name") else c for c in self.client.list_collections())

    def open_shelf(self, name: str, embedder: Embedder, create: bool = False):
        """Open a shelf. A missing shelf is an error unless create=True (never silently empty).
        A shelf remembers its embedding model; mixing models would give meaningless results."""
        if create:
            col = self.client.get_or_create_collection(
                name, metadata={"hnsw:space": "cosine", "embedder": embedder.name}
            )
        else:
            try:
                col = self.client.get_collection(name)
            except Exception as exc:
                raise ShelfNotFound(
                    f"Shelf '{name}' does not exist. Existing shelves: {self.list_shelves() or 'none'}"
                ) from exc
        used = (col.metadata or {}).get("embedder")
        if used and used != embedder.name:
            raise RuntimeError(
                f"Shelf '{name}' was built with embedder '{used}', but '{embedder.name}' is configured. "
                f"Use the same model, or re-ingest into a new shelf."
            )
        return col

    # -- writing ---------------------------------------------------------
    @staticmethod
    def has_book(col, book_id: str) -> bool:
        return bool(col.get(where={"book_id": book_id}, limit=1, include=[])["ids"])

    @staticmethod
    def add_chunks(col, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        metas = []
        for c in chunks:
            m = asdict(c)
            m.pop("text"), m.pop("chunk_id")
            metas.append(m)
        step = 500
        for i in range(0, len(chunks), step):
            col.add(
                ids=[c.chunk_id for c in chunks[i : i + step]],
                documents=[c.text for c in chunks[i : i + step]],
                embeddings=embeddings[i : i + step],
                metadatas=metas[i : i + step],
            )

    @staticmethod
    def remove_book(col, book_id: str) -> None:
        col.delete(where={"book_id": book_id})

    # -- reading ---------------------------------------------------------
    @staticmethod
    def list_books(col) -> list[dict[str, Any]]:
        """Distinct books on a shelf, with their chapter counts."""
        data = col.get(include=["metadatas"])
        books: dict[str, dict[str, Any]] = {}
        for m in data["metadatas"]:
            b = books.setdefault(
                m["book_id"],
                {
                    "book_id": m["book_id"],
                    "title": m["title"],
                    "author": m["author"],
                    "language": m["language"],
                    "source_file": m["source_file"],
                    "chapters": 0,
                },
            )
            b["chapters"] = max(b["chapters"], m["chapter_index"])
        return sorted(books.values(), key=lambda b: (b["author"], b["title"]))
