import sys
from pathlib import Path

import pytest
from ebooklib import epub

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from papermind.config import Config  # noqa: E402

WORDS_A = "dragon castle sword knight mountain river forest".split()
WORDS_B = "starship nebula captain engine orbit quantum signal".split()


def para(words, n, seed):
    return " ".join(words[(seed + i) % len(words)] for i in range(n)) + "."


def make_epub(path: Path, title="Test Book", author="Ann Author", chapters=None, lang="en"):
    chapters = chapters or []
    book = epub.EpubBook()
    book.set_identifier(f"id-{title}")
    book.set_title(title)
    book.set_language(lang)
    book.add_author(author)
    items = []
    cover = epub.EpubHtml(title="Copyright", file_name="copy.xhtml", lang=lang)
    cover.content = "<html><body><p>All rights reserved.</p></body></html>"
    book.add_item(cover)
    items.append(cover)
    for i, (head, paras) in enumerate(chapters, 1):
        c = epub.EpubHtml(title=head, file_name=f"ch{i}.xhtml", lang=lang)
        body = "".join(f"<p>{p}</p>" for p in paras)
        c.content = f"<html><body><h1>{head}</h1>{body}</body></html>"
        book.add_item(c)
        items.append(c)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + items
    epub.write_epub(str(path), book)
    return path


@pytest.fixture
def cfg(tmp_path):
    return Config(
        chroma_path=str(tmp_path / "chroma"),
        embedder="hash",
        min_chapter_words=50,
        chunk_words=80,
        chunk_overlap_words=15,
    )


@pytest.fixture
def fantasy_epub(tmp_path):
    chapters = [
        ("The Beginning", [para(WORDS_A, 60, i) for i in range(3)]),
        ("The Road", [para(WORDS_A, 60, i + 2) + " Gandalf appears." for i in range(3)]),
        ("The End", [para(WORDS_A, 60, i + 4) + " The unique-word zymurgy ends it." for i in range(3)]),
    ]
    return make_epub(tmp_path / "fantasy_book.epub", "The Dragon Road", "Ann Author", chapters)


@pytest.fixture
def scifi_epub(tmp_path):
    chapters = [
        ("Launch", [para(WORDS_B, 60, i) for i in range(3)]),
        ("Orbit", [para(WORDS_B, 60, i + 3) for i in range(3)]),
    ]
    return make_epub(tmp_path / "scifi_book.epub", "Star Drift", "Bob Writer", chapters)
