import os
import stat
import zipfile
from pathlib import Path

import pytest

from papermind.ingest import collect, main as ingest_main
from papermind.naming import match_existing_shelf, normalize_author, shelf_slug
from papermind.readers import book_format, read_book
from papermind.readers.common import ReaderError
from papermind.store import Store
from papermind.embeddings import HashEmbedder

from conftest import WORDS_A, WORDS_B, make_epub, para


def fb2_xml(title="Dune Road", first="Frank", last="Writer", lang="en", words=WORDS_A, encoding="utf-8"):
    def sec(name, seed, nested=""):
        ps = "".join(f"<p>{para(words, 60, seed + i)}</p>" for i in range(3))
        return f"<section><title><p>{name}</p></title>{ps}{nested}</section>"

    return (
        f'<?xml version="1.0" encoding="{encoding}"?>'
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
        f"<description><title-info><author><first-name>{first}</first-name><last-name>{last}</last-name></author>"
        f"<book-title>{title}</book-title><lang>{lang}</lang></title-info></description>"
        f"<body><section><title><p>Part One</p></title>{sec('One', 0)}{sec('Two', 2)}</section>"
        f"{sec('Three', 4)}</body>"
        '<body name="notes"><section><title><p>1</p></title><p>FOOTNOTE TEXT</p></section></body>'
        "</FictionBook>"
    )


def stub_tool(bindir: Path, name: str, script: str) -> None:
    bindir.mkdir(exist_ok=True)
    f = bindir / name
    f.write_text("#!/bin/sh\n" + script)
    f.chmod(f.stat().st_mode | stat.S_IEXEC)


# ---- format detection ---------------------------------------------------------------

def test_format_matching_is_case_insensitive():
    assert book_format("A Book.EPUB") == "epub"
    assert book_format("b.Fb2") == "fb2"
    assert book_format("c.FB2.ZIP") == "fb2"
    assert book_format("d.DjVu") == "djvu"
    assert book_format("e.MOBI") == "calibre"
    assert book_format("f.xyz") is None
    assert book_format("g.zip") is None


# ---- FB2 ----------------------------------------------------------------------------

def test_fb2_chapters_metadata_and_notes_ignored(tmp_path):
    f = tmp_path / "dune road.fb2"
    f.write_text(fb2_xml(), encoding="utf-8")
    book = read_book(f, min_chapter_words=50)
    assert (book.title, book.author, book.language) == ("Dune Road", "Frank Writer", "en")
    assert [c.title for c in book.chapters] == ["One", "Two", "Three"]
    assert all("FOOTNOTE" not in c.text for c in book.chapters)


def test_fb2_windows1251_russian(tmp_path):
    ru = "Это был очень длинный и странный день в нашем городе".split()
    xml = fb2_xml("Книга", "Иван", "Автор", "ru", ru, encoding="windows-1251")
    f = tmp_path / "ru.fb2"
    f.write_bytes(xml.encode("cp1251"))
    book = read_book(f, 50)
    assert book.title == "Книга" and book.author == "Иван Автор" and book.language == "ru"
    assert "странный" in book.chapters[0].text


@pytest.mark.parametrize("name", ["book.fb2.zip", "book.fbz"])
def test_fb2_in_zip(tmp_path, name):
    f = tmp_path / name
    with zipfile.ZipFile(f, "w") as zf:
        zf.writestr("inner.fb2", fb2_xml())
    assert read_book(f, 50).title == "Dune Road"


# ---- TXT ----------------------------------------------------------------------------

def test_txt_headings_and_cp1251(tmp_path):
    ru = " ".join(["слово"] * 60)
    text = f"Глава 1\n\n{ru}\n\n{ru}\n\nГлава 2\n\n{ru}\n\n{ru}\n"
    f = tmp_path / "old.txt"
    f.write_bytes(text.encode("cp1251"))
    book = read_txt_book(f)
    assert [c.title for c in book.chapters] == ["Глава 1", "Глава 2"]
    assert book.language == "ru"


def read_txt_book(f):
    return read_book(f, min_chapter_words=50)


def test_txt_without_headings_is_cut_into_parts(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("\n\n".join(para(WORDS_A, 100, i) for i in range(80)), encoding="utf-8")
    book = read_txt_book(f)
    assert len(book.chapters) >= 2 and book.chapters[0].title == "part 1"


# ---- DjVu and Calibre (with stand-in tools) -----------------------------------------

def test_djvu_with_stub_tool(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    stub_tool(bindir, "djvutxt", 'printf "First page about a dragon.\\fSecond page about a castle."\n')
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    f = tmp_path / "scan.DJVU"
    f.write_bytes(b"AT&TFORM")
    book = read_book(f)
    assert book.chapters and "dragon" in book.chapters[0].text and book.chapters[0].title == "pages 1-2"


def test_djvu_without_tool_gives_install_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    f = tmp_path / "scan.djvu"
    f.write_bytes(b"x")
    with pytest.raises(ReaderError, match="djvulibre"):
        read_book(f)


def test_calibre_fallback_with_stub_tool(tmp_path, monkeypatch):
    src_epub = make_epub(tmp_path / "prebuilt.epub", "Converted Title", "Cal Author",
                         [("One", [para(WORDS_B, 60, i) for i in range(3)])])
    bindir = tmp_path / "bin"
    stub_tool(bindir, "ebook-convert", f'cp "{src_epub}" "$2"\n')
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    f = tmp_path / "My Book With Spaces.MOBI"
    f.write_bytes(b"BOOKMOBI-not-real")
    book = read_book(f, 50)
    assert book.source_file == "My Book With Spaces.MOBI"   # identity from the original file
    assert book.title == "Converted Title" and book.chapters


def test_calibre_missing_gives_install_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    f = tmp_path / "x.azw3"
    f.write_bytes(b"x")
    with pytest.raises(ReaderError, match="calibre"):
        read_book(f)


# ---- names --------------------------------------------------------------------------

def test_shelf_slug():
    assert shelf_slug("Science Fiction") == "Science-Fiction"
    assert shelf_slug("Фантастика") == "Fantastika"
    assert shelf_slug("SF") == "SF-shelf"
    assert shelf_slug("!!") .startswith("shelf-")
    assert shelf_slug("  Disc World  ") == "Disc-World"
    assert shelf_slug("a..b") == "a.b"
    assert shelf_slug("DiscWorld") == "DiscWorld"       # valid names are never changed


def test_match_existing_shelf_ignores_letter_case_only():
    assert match_existing_shelf("discworld", ["DiscWorld", "scifi"]) == "DiscWorld"
    assert match_existing_shelf("DiscWorld", ["DiscWorld"]) == "DiscWorld"
    assert match_existing_shelf("new", ["DiscWorld"]) == "new"


def test_normalize_author():
    assert normalize_author("Pratchett, Terry") == "Terry Pratchett"
    assert normalize_author("  Terry   Pratchett ") == "Terry Pratchett"
    assert normalize_author("Gaiman, Neil & Pratchett, Terry") == "Gaiman, Neil & Pratchett, Terry"
    assert normalize_author("") == "Unknown"


# ---- batch ingest -------------------------------------------------------------------

@pytest.fixture
def library(tmp_path):
    root = tmp_path / "My Library"
    a = root / "fantasy" / "Terry Pratchett "          # note the trailing space
    b = root / "Science Fiction" / "Isaac Asimov"
    a.mkdir(parents=True), b.mkdir(parents=True)
    make_epub(a / "The Colour Of Magic.EPUB", "Colour", "Pratchett, Terry",
              [("One", [para(WORDS_A, 60, i) for i in range(3)])])
    (b / "Foundation.FB2").write_text(fb2_xml("Foundation", "I.", "A."), encoding="utf-8")
    (root / "fantasy" / ".hidden.epub").write_bytes(b"x")
    (root / "fantasy" / "._junk.epub").write_bytes(b"x")
    (root / "loose.txt").write_text("loose", encoding="utf-8")
    return root


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERMIND_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("PAPERMIND_EMBEDDER", "hash")
    monkeypatch.setenv("PAPERMIND_MIN_CHAPTER_WORDS", "50")
    return tmp_path / "chroma"


def test_collect_skips_junk_and_dedupes(library):
    files = [p.name for p, _ in collect([library / "fantasy", library / "fantasy"])]
    assert files == ["The Colour Of Magic.EPUB"]


def test_auto_shelves_batch_with_author_from_folder(library, cli_env, capsys):
    assert ingest_main(["--auto-shelves", str(library), "--author-from-folder"]) == 0
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    store = Store(str(cli_env))
    assert store.list_shelves() == ["Science-Fiction", "fantasy"]
    fantasy = store.open_shelf("fantasy", HashEmbedder())
    sci = store.open_shelf("Science-Fiction", HashEmbedder())
    assert {b["author"] for b in Store.list_books(fantasy)} == {"Terry Pratchett"}
    assert {b["author"] for b in Store.list_books(sci)} == {"Isaac Asimov"}   # folder beats metadata
    assert "Done: 2 ok" in out
    assert "directly in" in err and "--shelf" in err   # the loose file is mentioned, not ingested


def test_without_the_flag_metadata_wins_and_is_normalised(library, cli_env):
    assert ingest_main(["--auto-shelves", str(library)]) == 0
    fantasy = Store(str(cli_env)).open_shelf("fantasy", HashEmbedder())
    assert {b["author"] for b in Store.list_books(fantasy)} == {"Terry Pratchett"}  # 'Pratchett, Terry'


def test_dry_run_writes_nothing(library, cli_env, capsys):
    assert ingest_main(["--auto-shelves", str(library), "--author-from-folder", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would add" in out and "Foundation.FB2" in out and "author: Isaac Asimov" in out
    assert not cli_env.exists()


def test_folder_in_other_letter_case_reuses_existing_shelf(tmp_path, cli_env, capsys):
    store = Store(str(cli_env))
    store.open_shelf("DiscWorld", HashEmbedder(), create=True)
    folder = tmp_path / "lib" / "discworld"
    folder.mkdir(parents=True)
    make_epub(folder / "b.epub", "B", "Ann", [("One", [para(WORDS_A, 60, i) for i in range(3)])])
    assert ingest_main(["--auto-shelves", str(tmp_path / "lib")]) == 0
    assert Store(str(cli_env)).list_shelves() == ["DiscWorld"]
    assert "existing shelf" in capsys.readouterr().out


def test_author_override_and_shelf_name_cleanup(tmp_path, cli_env):
    f = make_epub(tmp_path / "b.epub", "B", "Wrong Meta", [("One", [para(WORDS_A, 60, i) for i in range(3)])])
    assert ingest_main(["--shelf", "Sci Fi", "--author", "Right Name", str(f)]) == 0
    col = Store(str(cli_env)).open_shelf("Sci-Fi", HashEmbedder())
    assert {b["author"] for b in Store.list_books(col)} == {"Right Name"}


def test_failing_book_does_not_stop_the_batch(tmp_path, cli_env, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))  # no Calibre
    d = tmp_path / "lib" / "shelfy"
    d.mkdir(parents=True)
    (d / "broken.mobi").write_bytes(b"x")
    make_epub(d / "good.epub", "G", "Ann", [("One", [para(WORDS_A, 60, i) for i in range(3)])])
    assert ingest_main(["--auto-shelves", str(tmp_path / "lib")]) == 1   # non-zero: something failed
    out = capsys.readouterr().out
    assert "1 ok" in out and "1 fail" in out and "needs attention" in out


def test_doctor_runs(capsys):
    assert ingest_main(["--doctor"]) == 0
    out = capsys.readouterr().out
    assert "ebook-convert" in out and "djvutxt" in out
