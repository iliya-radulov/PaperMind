"""CLI: add books to a shelf.

    python -m papermind.ingest --shelf fantasy books/fantasy
    python -m papermind.ingest --shelf scifi books/scifi/dune.epub --replace
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chunking import chunk_book
from .config import Config, load_config
from .embeddings import Embedder, make_embedder
from .readers import SUPPORTED, read_book
from .store import Store


def find_books(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            found.extend(sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED))
        elif p.suffix.lower() in SUPPORTED:
            found.append(p)
        else:
            print(f"skip (not epub/pdf): {p}", file=sys.stderr)
    return found


def ingest_file(cfg: Config, store: Store, col, embedder: Embedder, path: Path, replace: bool = False) -> str:
    book = read_book(path, cfg.min_chapter_words)
    if not book.chapters:
        return f"EMPTY  {path.name} (no text found; scanned PDF? needs OCR)"
    if Store.has_book(col, book.book_id):
        if not replace:
            return f"SKIP   {path.name} (already on this shelf)"
        Store.remove_book(col, book.book_id)
    chunks = chunk_book(book, cfg.chunk_words, cfg.chunk_overlap_words)
    vectors = embedder.embed([c.text for c in chunks])
    Store.add_chunks(col, chunks, vectors)
    return f"OK     {path.name}: {book.title} / {book.author} [{book.language}] {len(book.chapters)} ch, {len(chunks)} chunks"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add epub/pdf books to a PaperMind shelf.")
    ap.add_argument("paths", nargs="+", help="files or folders")
    ap.add_argument("--shelf", required=True, help="shelf name, e.g. fantasy")
    ap.add_argument("--replace", action="store_true", help="re-ingest books already on the shelf")
    ap.add_argument("--config", help="path to papermind.toml")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    embedder = make_embedder(cfg)
    store = Store(cfg.chroma_path)
    col = store.open_shelf(args.shelf, embedder, create=True)

    books = find_books(args.paths)
    if not books:
        print("No epub/pdf files found.", file=sys.stderr)
        return 1
    for i, path in enumerate(books, 1):
        print(f"[{i}/{len(books)}] ", end="", flush=True)
        try:
            print(ingest_file(cfg, store, col, embedder, path, args.replace), flush=True)
        except Exception as exc:  # one broken book must not stop a long run
            print(f"FAIL   {path.name}: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
