"""Book readers. Native readers: epub, pdf, fb2 (+zip), txt, djvu. Everything else Calibre can
read (mobi, azw3, docx, rtf, ...) goes through `ebook-convert` if Calibre is installed."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..models import Book
from .common import ReaderError, file_hash

NATIVE = {
    ".epub": "epub",
    ".pdf": "pdf",
    ".fb2": "fb2",
    ".fbz": "fb2",
    ".txt": "txt",
    ".djvu": "djvu",
    ".djv": "djvu",
}
VIA_CALIBRE = {
    ".mobi", ".azw", ".azw3", ".azw4", ".prc", ".pdb", ".lit", ".lrf",
    ".docx", ".odt", ".rtf", ".htmlz", ".html", ".htm", ".chm", ".txtz",
}


def book_format(path: str | Path) -> str | None:
    """Format key for a file, matching the extension in any letter case (Linux is case-sensitive,
    books are not: 'Book.EPUB', 'book.Fb2' and 'book.fb2.ZIP' all work). None = unsupported."""
    name = Path(path).name.lower()
    if name.endswith(".fb2.zip"):
        return "fb2"
    suffix = Path(name).suffix
    if suffix in NATIVE:
        return NATIVE[suffix]
    if suffix in VIA_CALIBRE:
        return "calibre"
    return None


def is_supported(path: str | Path) -> bool:
    return book_format(path) is not None


def _convert_with_calibre(path: Path, workdir: Path) -> Path:
    exe = shutil.which("ebook-convert")
    if not exe:
        raise ReaderError(
            f"{path.name}: this format needs Calibre's 'ebook-convert'. Install Calibre "
            "(Debian/Ubuntu: sudo apt install calibre), or convert the book to epub yourself."
        )
    out = workdir / "converted.epub"
    try:
        proc = subprocess.run([exe, str(path), str(out)], capture_output=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        raise ReaderError(f"{path.name}: Calibre conversion timed out") from exc
    if proc.returncode != 0 or not out.exists():
        raise ReaderError(f"{path.name}: Calibre could not convert it: {proc.stderr.decode(errors='replace')[-200:]}")
    return out


def read_book(path: str | Path, min_chapter_words: int = 120) -> Book:
    path = Path(path)
    fmt = book_format(path)
    if fmt == "epub":
        from .epub import read_epub
        return read_epub(path, min_chapter_words)
    if fmt == "pdf":
        from .pdf import read_pdf
        return read_pdf(path)
    if fmt == "fb2":
        from .fb2 import read_fb2
        return read_fb2(path, min_chapter_words)
    if fmt == "txt":
        from .txt import read_txt
        return read_txt(path, min_chapter_words)
    if fmt == "djvu":
        from .djvu import read_djvu
        return read_djvu(path)
    if fmt == "calibre":
        from .epub import read_epub
        with tempfile.TemporaryDirectory() as tmp:
            converted = _convert_with_calibre(path, Path(tmp))
            book = read_epub(converted, min_chapter_words)
        # identity comes from the original file, not from the temporary conversion
        book.book_id = file_hash(path)
        book.source_file = path.name
        if book.title == "converted":
            book.title = path.stem
        return book
    raise ReaderError(f"Unsupported file type: {path.name}")
