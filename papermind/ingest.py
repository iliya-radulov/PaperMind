"""CLI: add books to shelves, one file, one folder, or a whole library at once.

    python -m papermind.ingest --shelf fantasy books/fantasy
    python -m papermind.ingest --auto-shelves books --author-from-folder
    python -m papermind.ingest --auto-shelves books --dry-run
    python -m papermind.ingest --doctor

With --auto-shelves ROOT every sub-folder of ROOT becomes a shelf. With --author-from-folder the
folder a book sits in (ROOT/fantasy/Terry Pratchett/Mort.epub) is used as its author.
Extensions are matched in any letter case; spaces in names are fine.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .chunking import chunk_book
from .config import Config, load_config
from .embeddings import Embedder, make_embedder
from .naming import match_existing_shelf, normalize_author, shelf_slug
from .readers import NATIVE, VIA_CALIBRE, book_format, is_supported, read_book
from .store import Store

Entry = tuple[Path, "Path | None"]  # (book file, folder it was found under, if any)


def _skippable(rel_parts: tuple[str, ...]) -> bool:
    # hidden files/folders, macOS resource forks (._x), Office lock files (~$x)
    return any(p.startswith((".", "~$")) for p in rel_parts)


def collect(paths: list[str | Path]) -> list[Entry]:
    found: list[Entry] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and is_supported(f) and not _skippable(f.relative_to(p).parts):
                    if f.resolve() not in seen:
                        seen.add(f.resolve())
                        found.append((f, p))
        elif p.is_file() and is_supported(p):
            if p.resolve() not in seen:
                seen.add(p.resolve())
                found.append((p, None))
        else:
            print(f"skip (not a supported book file): {p}", file=sys.stderr)
    return found


def folder_author(path: Path, base: Path | None) -> str | None:
    """Author from the folder the book is in, if that folder is below the base folder."""
    if base is None or path.parent == base:
        return None
    return path.parent.name.strip() or None


def ingest_file(
    cfg: Config,
    store: Store,
    col,
    embedder: Embedder,
    path: Path,
    replace: bool = False,
    author: str | None = None,
) -> str:
    """author, when given, replaces whatever the file's metadata says."""
    book = read_book(path, cfg.min_chapter_words)
    book.author = author.strip() if author else normalize_author(book.author)
    if not book.chapters:
        return f"EMPTY  {path.name} (no text found; a scan without a text layer needs OCR first)"
    if Store.has_book(col, book.book_id):
        if not replace:
            return f"SKIP   {path.name} (already on this shelf)"
        Store.remove_book(col, book.book_id)
    chunks = chunk_book(book, cfg.chunk_words, cfg.chunk_overlap_words)
    vectors = embedder.embed([c.text for c in chunks])
    Store.add_chunks(col, chunks, vectors)
    return (
        f"OK     {path.name}: {book.title} / {book.author} [{book.language}] "
        f"{len(book.chapters)} ch, {len(chunks)} chunks"
    )


def doctor() -> int:
    print("Formats read natively: " + ", ".join(sorted(NATIVE)) + ", .fb2.zip")
    print("Formats read through Calibre: " + ", ".join(sorted(VIA_CALIBRE)))
    for exe, what, hint in [
        ("ebook-convert", "Calibre conversion (mobi, azw3, docx, rtf, ...)", "sudo apt install calibre"),
        ("djvutxt", "DjVu text extraction", "sudo apt install djvulibre-bin"),
    ]:
        path = shutil.which(exe)
        print(f"  {'found  ' if path else 'MISSING'} {exe}: {what}" + (f" -> {path}" if path else f"  [{hint}]"))
    return 0


def plan(args, cfg: Config) -> dict[str, list[Entry]]:
    """Which files go to which shelf."""
    groups: dict[str, list[Entry]] = {}
    if args.auto_shelves:
        root = Path(args.auto_shelves)
        if not root.is_dir():
            raise SystemExit(f"Not a folder: {root}")
        loose = [(f, None) for f in sorted(root.iterdir()) if f.is_file() and is_supported(f) and not _skippable((f.name,))]
        if loose:
            if args.shelf:
                groups.setdefault(args.shelf, []).extend(loose)
            else:
                print(f"note: {len(loose)} file(s) directly in {root} skipped (use --shelf NAME to add them)", file=sys.stderr)
        for sub in sorted(d for d in root.iterdir() if d.is_dir() and not _skippable((d.name,))):
            entries = collect([sub])
            if entries:
                groups.setdefault(sub.name, []).extend(entries)
    if args.paths:
        if not args.shelf:
            raise SystemExit("--shelf is required when you give files or folders")
        groups.setdefault(args.shelf, []).extend(collect(args.paths))
    return groups


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add books to PaperMind shelves.")
    ap.add_argument("paths", nargs="*", help="files or folders (use with --shelf)")
    ap.add_argument("--shelf", help="shelf name, e.g. fantasy")
    ap.add_argument("--auto-shelves", metavar="ROOT", help="every sub-folder of ROOT becomes a shelf")
    ap.add_argument("--author-from-folder", action="store_true",
                    help="use the folder a book sits in as its author (overrides file metadata)")
    ap.add_argument("--author", help="set this author for every book in this run")
    ap.add_argument("--replace", action="store_true", help="re-ingest books already on the shelf")
    ap.add_argument("--dry-run", action="store_true", help="only list what would be added")
    ap.add_argument("--doctor", action="store_true", help="show which formats and tools are available")
    ap.add_argument("--config", help="path to papermind.toml")
    args = ap.parse_args(argv)

    if args.doctor:
        return doctor()
    if not args.paths and not args.auto_shelves:
        ap.error("give files/folders with --shelf, or --auto-shelves ROOT (or --doctor)")

    cfg = load_config(args.config)
    groups = plan(args, cfg)
    if not groups:
        print("No supported book files found.", file=sys.stderr)
        return 1

    store = None if args.dry_run else Store(cfg.chroma_path)
    existing = store.list_shelves() if store else []
    embedder = None
    counts = {"OK": 0, "SKIP": 0, "EMPTY": 0, "FAIL": 0}
    failed: list[str] = []

    for requested, entries in groups.items():
        slug = shelf_slug(requested)
        name = match_existing_shelf(slug, existing)
        if name != requested:
            print(f"shelf '{requested}' -> '{name}'" + (" (existing shelf, same name apart from letter case)" if name != slug else ""))
        print(f"\n== shelf '{name}': {len(entries)} file(s)")
        col = None
        if not args.dry_run:
            embedder = embedder or make_embedder(cfg)
            col = store.open_shelf(name, embedder, create=True)
            existing = store.list_shelves()
        for i, (path, base) in enumerate(entries, 1):
            who = args.author or (folder_author(path, base) if args.author_from_folder else None)
            if args.dry_run:
                print(f"[{i}/{len(entries)}] would add {path}  [{book_format(path)}]" + (f"  author: {who}" if who else ""))
                continue
            print(f"[{i}/{len(entries)}] ", end="", flush=True)
            try:
                line = ingest_file(cfg, store, col, embedder, path, args.replace, author=who)
            except Exception as exc:  # one broken book must not stop a long run
                line = f"FAIL   {path.name}: {exc}"
            counts[line.split()[0]] += 1
            if line.startswith(("FAIL", "EMPTY")):
                failed.append(line)
            print(line, flush=True)

    if not args.dry_run:
        print("\nDone: " + ", ".join(f"{v} {k.lower()}" for k, v in counts.items() if v))
        for line in failed:
            print("  needs attention:", line)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
