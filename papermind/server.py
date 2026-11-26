"""Local web app. Run:  python -m papermind.server"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import answer as answer_mod
from .config import Config, load_config
from .embeddings import Embedder, make_embedder
from .retrieve import retrieve
from .store import ShelfNotFound, Store

WEB_DIR = Path(__file__).parent / "web"


def create_app(cfg: Config | None = None, embedder: Embedder | None = None, chat_fn=None) -> Flask:
    cfg = cfg or load_config()
    embedder = embedder or make_embedder(cfg)
    chat_fn = chat_fn or answer_mod.generate
    store = Store(cfg.chroma_path)
    app = Flask(__name__, static_folder=None)

    def passages_json(passages):
        return [{**asdict(p), "cite": p.cite} for p in passages]

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/api/shelves")
    def shelves():
        return jsonify({"shelves": store.list_shelves()})

    @app.get("/api/books")
    def books():
        try:
            col = store.open_shelf(request.args.get("shelf", ""), embedder)
        except ShelfNotFound as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify({"books": Store.list_books(col)})

    def run(do_answer: bool):
        body = request.get_json(silent=True) or {}
        question = (body.get("question") or "").strip()
        if not question:
            return jsonify({"error": "question is required"}), 400
        try:
            col = store.open_shelf(body.get("shelf", ""), embedder)
            max_chapter = body.get("max_chapter")
            passages = retrieve(
                col,
                embedder,
                question,
                k=int(body.get("k") or cfg.top_k),
                author=body.get("author") or None,
                book_id=body.get("book_id") or None,
                language=body.get("language") or None,
                max_chapter=int(max_chapter) if max_chapter not in (None, "") else None,
            )
        except ShelfNotFound as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502
        result = {"passages": passages_json(passages)}
        if do_answer:
            try:
                result.update(chat_fn(cfg, question, passages))
            except RuntimeError as exc:
                return jsonify({"error": str(exc), "passages": result["passages"]}), 502
        return jsonify(result)

    @app.post("/api/ask")
    def ask():
        return run(True)

    @app.post("/api/search")
    def search():
        return run(False)

    return app


def main() -> None:
    cfg = load_config()
    create_app(cfg).run(host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
