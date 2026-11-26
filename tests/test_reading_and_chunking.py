from papermind.chunking import chunk_book, chunk_text
from papermind.langtag import detect_language
from papermind.readers import read_book

from conftest import make_epub


def test_epub_chapters_and_metadata(fantasy_epub):
    book = read_book(fantasy_epub, min_chapter_words=50)
    assert book.title == "The Dragon Road"
    assert book.author == "Ann Author"
    assert book.language == "en"
    # the tiny copyright page is folded away, three real chapters remain
    assert [c.title for c in book.chapters] == ["The Beginning", "The Road", "The End"]
    assert [c.index for c in book.chapters] == [1, 2, 3]


def test_book_id_is_content_hash_not_name(fantasy_epub, tmp_path):
    copy = tmp_path / "other_name.epub"
    copy.write_bytes(fantasy_epub.read_bytes())
    assert read_book(copy, 50).book_id == read_book(fantasy_epub, 50).book_id


def test_russian_detected(tmp_path):
    text = "Это был очень длинный и странный день в городе. " * 5
    p = make_epub(tmp_path / "ru.epub", "Книга", "Автор", [("Глава", [text] * 3)], lang="ru")
    assert read_book(p, 50).language == "ru"
    assert detect_language("Hello there, a plain English sentence.") == "en"


def test_chunks_respect_size_and_cover_all_text():
    paras = [f"p{i} " + "word " * 59 for i in range(10)]
    chunks = chunk_text("\n\n".join(paras), target_words=100, overlap_words=20)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 100 + 20 for c in chunks)
    joined = "\n\n".join(chunks)
    assert all(f"p{i} " in joined for i in range(10))


def test_overlong_paragraph_is_split():
    text = " ".join(f"Sentence number {i} ends here." for i in range(200))
    chunks = chunk_text(text, target_words=60, overlap_words=10)
    assert len(chunks) > 5
    assert all(len(c.split()) <= 70 for c in chunks)


def test_chunk_ids_unique_and_carry_chapter(fantasy_epub):
    book = read_book(fantasy_epub, 50)
    chunks = chunk_book(book, 80, 15)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert {c.chapter_index for c in chunks} == {1, 2, 3}


def test_single_file_epub_with_many_chapters_is_split(tmp_path):
    """Many ebooks put the whole text in one XHTML file with h2 headings."""
    from ebooklib import epub

    body = "".join(
        f"<h2>Chapter {i}</h2>" + "".join(f"<p>{'word ' * 40}number {i}.</p>" for _ in range(3))
        for i in range(1, 5)
    )
    book = epub.EpubBook()
    book.set_identifier("one-file")
    book.set_title("One File")
    book.set_language("en")
    book.add_author("Z")
    c = epub.EpubHtml(title="all", file_name="all.xhtml")
    c.content = f"<html><body>{body}</body></html>"
    book.add_item(c)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c]
    path = tmp_path / "one.epub"
    epub.write_epub(str(path), book)
    chapters = read_book(path, min_chapter_words=100).chapters
    assert [c.title for c in chapters] == [f"Chapter {i}" for i in range(1, 5)]


def test_pdf_reader_groups_pages(tmp_path):
    from papermind.readers.pdf import read_pdf

    text = "A quiet village sat beside the sea and nothing ever happened there"
    stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    path = tmp_path / "tiny.pdf"
    path.write_bytes(out)
    book = read_pdf(path)
    assert book.title == "tiny"
    assert len(book.chapters) == 1 and "quiet village" in book.chapters[0].text
    assert book.chapters[0].title == "pages 1-1"
