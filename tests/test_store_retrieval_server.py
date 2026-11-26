import pytest

from papermind.embeddings import HashEmbedder
from papermind.ingest import ingest_file, main as ingest_main
from papermind.retrieve import build_where, retrieve
from papermind.server import create_app
from papermind.store import ShelfNotFound, Store


@pytest.fixture
def shelf(cfg, fantasy_epub, scifi_epub):
    emb = HashEmbedder()
    store = Store(cfg.chroma_path)
    col = store.open_shelf("mixed", emb, create=True)
    for p in (fantasy_epub, scifi_epub):
        assert ingest_file(cfg, store, col, emb, p).startswith("OK")
    return store, col, emb


def test_ingest_is_idempotent(cfg, shelf, fantasy_epub):
    store, col, emb = shelf
    assert ingest_file(cfg, store, col, emb, fantasy_epub).startswith("SKIP")
    n = col.count()
    assert ingest_file(cfg, store, col, emb, fantasy_epub, replace=True).startswith("OK")
    assert col.count() == n


def test_retrieval_finds_the_right_book(shelf):
    _, col, emb = shelf
    top = retrieve(col, emb, "dragon castle sword knight", k=3)
    assert top[0].title == "The Dragon Road"
    top = retrieve(col, emb, "starship nebula captain", k=3)
    assert top[0].title == "Star Drift"


def test_spoiler_limit(shelf):
    _, col, emb = shelf
    book_id = retrieve(col, emb, "zymurgy", k=1)[0].book_id
    free = retrieve(col, emb, "unique-word zymurgy ends it", k=10, book_id=book_id)
    assert any(p.chapter_index == 3 for p in free)
    limited = retrieve(col, emb, "unique-word zymurgy ends it", k=10, book_id=book_id, max_chapter=2)
    assert limited and all(p.chapter_index <= 2 for p in limited)


def test_max_chapter_needs_a_book():
    with pytest.raises(ValueError):
        build_where(max_chapter=2)


def test_missing_shelf_is_an_error_not_an_empty_shelf(cfg):
    store = Store(cfg.chroma_path)
    with pytest.raises(ShelfNotFound):
        store.open_shelf("nope", HashEmbedder())
    assert store.list_shelves() == []


def test_embedder_mismatch_is_refused(cfg, shelf):
    store, _, _ = shelf

    class Other(HashEmbedder):
        name = "other-model"

    with pytest.raises(RuntimeError, match="built with embedder"):
        store.open_shelf("mixed", Other())


def test_cli_ingest_folder(cfg, tmp_path, fantasy_epub, monkeypatch, capsys):
    monkeypatch.setenv("PAPERMIND_CHROMA_PATH", str(tmp_path / "cli_chroma"))
    monkeypatch.setenv("PAPERMIND_EMBEDDER", "hash")
    monkeypatch.setenv("PAPERMIND_MIN_CHAPTER_WORDS", "50")
    assert ingest_main(["--shelf", "fantasy", str(fantasy_epub.parent)]) == 0
    assert "OK" in capsys.readouterr().out


def test_server_endpoints(cfg, shelf):
    def fake_chat(cfg_, question, passages):
        return {"answer": f"stub answer using {len(passages)} passages [1]", "prompt_tokens": 10, "truncated": False}

    app = create_app(cfg, embedder=HashEmbedder(), chat_fn=fake_chat)
    c = app.test_client()
    assert c.get("/").status_code == 200
    assert c.get("/api/shelves").get_json()["shelves"] == ["mixed"]
    books = c.get("/api/books?shelf=mixed").get_json()["books"]
    assert {b["title"] for b in books} == {"The Dragon Road", "Star Drift"}
    assert max(b["chapters"] for b in books) == 3

    r = c.post("/api/ask", json={"shelf": "mixed", "question": "dragon castle", "k": 3})
    j = r.get_json()
    assert r.status_code == 200 and "stub answer" in j["answer"] and len(j["passages"]) == 3
    assert "chapter" not in j["passages"][0]["cite"] or "ch." in j["passages"][0]["cite"]

    assert c.post("/api/search", json={"shelf": "mixed", "question": "orbit"}).get_json().get("answer") is None
    assert c.post("/api/ask", json={"shelf": "mixed", "question": ""}).status_code == 400
    assert c.post("/api/ask", json={"shelf": "ghost", "question": "x"}).status_code == 404
    assert c.post("/api/ask", json={"shelf": "mixed", "question": "x", "max_chapter": 2}).status_code == 400


def test_prompt_contains_numbered_cited_passages(shelf):
    from papermind.answer import build_prompt

    _, col, emb = shelf
    ps = retrieve(col, emb, "dragon", k=2)
    prompt = build_prompt("Who is the dragon?", ps)
    assert "[1] The Dragon Road" in prompt and "[2]" in prompt and "ONLY" in prompt
