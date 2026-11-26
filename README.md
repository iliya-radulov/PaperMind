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

Put books anywhere (the `books/` folder is git-ignored, so your library never reaches GitHub).

**A whole library at once.** Arrange it as one folder per shelf, optionally one sub-folder per author:

```
books/
  fantasy/
    Terry Pratchett/         <- author (with --author-from-folder)
      Mort.epub
      Small Gods.FB2
  science fiction/
    Stanislaw Lem/
      Solaris.djvu
```

```bash
python -m papermind.ingest --auto-shelves books --author-from-folder --dry-run   # preview, writes nothing
python -m papermind.ingest --auto-shelves books --author-from-folder             # do it
python -m papermind.server
```

Each sub-folder of `books/` becomes a shelf. Re-running skips books already on the shelf (matched by
file content, not name), so you can add new books and run the same command again; `--replace`
re-ingests them. One broken book never stops the run: it is listed at the end.

**One shelf, files or folders:**

```bash
python -m papermind.ingest --shelf fantasy books/fantasy
python -m papermind.ingest --shelf scifi "books/scifi/Some Book.epub" --author "Some Author"
```

Open <http://127.0.0.1:5050> to ask.

**Names on Linux.** Extensions are matched in any letter case (`.EPUB`, `.Fb2`, `.fb2.ZIP`). Spaces and
odd characters in file and folder names are fine (quote paths with spaces in the shell). Hidden files,
macOS `._*` files and `~$*` lock files are skipped. Shelf names must be simple for Chroma, so a folder
called `Science Fiction` becomes the shelf `Science-Fiction` and a Cyrillic name is transliterated
(`Научная фантастика` becomes `Nauchnaya-fantastika`); the run prints each change. Letter case is
kept, but a folder that differs from an existing shelf only by case (`discworld` vs `DiscWorld`)
goes into the existing shelf instead of creating a second one.

**Authors.** The author comes from the file's metadata (`Pratchett, Terry` becomes `Terry Pratchett`).
PDF, TXT and DjVu files usually have none, so use `--author-from-folder` (the folder name wins over
metadata) or `--author "Name"` for the whole run. The author matters for the voice mode.

## Formats

| Format | How it is read |
|---|---|
| EPUB | natively, with chapters |
| FB2, FB2.ZIP, FBZ | natively, with chapters (old Windows-1251 files work) |
| PDF | natively, grouped into 10-page sections (needs a text layer) |
| TXT | natively; UTF-8 or Windows-1251; chapters found by "Chapter N"/"Глава N" headings |
| DjVu | text layer via `djvutxt` (`sudo apt install djvulibre-bin`) |
| MOBI, AZW3, DOCX, RTF, ODT, HTML, ... | converted to EPUB with Calibre's `ebook-convert` (`sudo apt install calibre`) |

`python -m papermind.ingest --doctor` shows which of these tools are installed. A scan with no text layer
(PDF or DjVu) is reported as EMPTY and needs OCR first, for example `ddjvu -format=pdf in.djvu out.pdf`
followed by `ocrmypdf out.pdf ocr.pdf`.

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
  readers/      epub, pdf, fb2, txt, djvu, Calibre fallback   books -> chapters
  naming.py                           shelf names, author normalisation
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
- Scans without a text layer (PDF, DjVu) are reported as empty; they need OCR first.
- Answers are one-shot; there is no chat history yet.
- Not tested against real Ollama models in the development environment; run the benchmark on
  your machine first.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
