# PaperMind

A local, private question-answering shelf for fiction (fantasy, science fiction, and more).
Add your own epub/PDF books, ask questions, and get answers grounded in passages from the
books, with book and chapter citations. Everything runs on your own machine with
[Ollama](https://ollama.com/) and [Chroma](https://www.trychroma.com/). No cloud, no API keys.

It is deliberately separate from any scientific-literature database: PaperMind has its own
local Chroma store (`./chroma_db`) and never connects to a server.

## What it does

- **Shelves:** one Chroma collection per shelf (`fantasy`, `scifi`, `russian`, ...).
- **Chapter-aware ingest:** epubs keep their chapter structure; PDFs are grouped into 10-page sections.
- **Citations:** every passage carries title, author and chapter; answers cite passages as `[1]`, `[2]`.
- **Spoiler limit:** pick a book and "read up to chapter N"; later chapters are never retrieved.
- **Multilingual:** bge-m3 embeddings handle English and Russian (and many other languages).
- **Honest failures:** a missing shelf is an error, never a silently empty one; a shelf refuses to be
  queried with a different embedding model than it was built with; the UI warns when the prompt
  filled the model's context window.
- **Benchmark:** measure retrieval quality (hit@k, MRR) on your own questions before trusting answers.

## Setup

Requires Python 3.11+ and Ollama.

```bash
ollama pull bge-m3
ollama pull qwen2.5:14b      # or any chat model that fits your GPU; set it in papermind.toml
```

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Optional settings: copy `papermind.example.toml` to `papermind.toml` and edit it
(every setting can also be set with a `PAPERMIND_<NAME>` environment variable).

## Use

Put books anywhere (the `books/` folder is git-ignored, so your library never reaches GitHub):

```bash
python -m papermind.ingest --shelf fantasy books/fantasy
python -m papermind.ingest --shelf scifi books/scifi/some_book.epub
python -m papermind.server
```

Open <http://127.0.0.1:5050>. Re-running ingest skips books already on the shelf
(matched by file content, not name); `--replace` re-ingests them.

## Two modes

- **About the books** (default): factual answers from the retrieved passages, with `[1]`, `[2]` citations.
- **In the author's voice**: ask an abstract question ("does the self need time?", "is honesty worth it?")
  and get a short piece the author might plausibly write, built from the passages retrieved from that
  author's own books. It is a pastiche, not a real statement by the author. The model is told to take
  ideas and voice from the passages, apply the outlook to questions the books never address without
  inventing facts or quotes, and end with a plain out-of-character `Grounding:` note saying which
  passages it drew on and whether the question went beyond them.

Style notes per author live in `papermind/personas.default.toml` (Vonnegut, Pratchett, Adams, Pelevin,
Dostoevsky). Add or change authors by creating `personas.toml` next to where you run the server
(same layout, entries with the same `name` replace the defaults). An author with no entry still works,
with a generic "use the voice of the passages" style. Voice mode uses `persona_top_k` (default 10)
and `persona_temperature` (default 0.7) from the config.

Passage labels say "section N", not "chapter N": an epub's title page, dedication and so on count as
sections, so the section number can be larger than the printed chapter number.

## Check retrieval before trusting answers

Copy `bench/questions.example.csv`, write 20-30 questions with a few exact words from the passage
that answers each (and a few `out_of_corpus` questions the books cannot answer), then:

```bash
python bench/run_benchmark.py bench/my_questions.csv
```

## Layout

```
papermind/
  readers/      epub.py, pdf.py       books -> chapters
  chunking.py                         paragraph-aware chunks with overlap
  embeddings.py                       Ollama bge-m3 (and a hash embedder for tests)
  store.py  retrieve.py  answer.py    Chroma shelves, filtered retrieval, cited answers
  ingest.py                           CLI
  server.py  web/index.html           local web app (JSON API under /api)
bench/                                retrieval benchmark
tests/                                pytest suite (no Ollama needed)
```

The JSON API (`/api/shelves`, `/api/books`, `/api/search`, `/api/ask`) is what other tools,
such as a podcast studio or a book analyzer, can call later.

## Known limits (first version)

- Language detection is script-based (Cyrillic vs Latin) plus the epub's own language tag.
- No cross-language query translation: ask in the language of the book you want to hit.
- Scanned PDFs without a text layer are reported as empty; they need OCR first.
- Answers are one-shot; there is no chat history yet.
- Not tested against real Ollama models in the development environment; run the benchmark on
  your machine first.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
