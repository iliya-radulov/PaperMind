"""Retrieval benchmark: does the right passage show up in the top-k?

    python bench/run_benchmark.py bench/questions.csv

CSV columns: question, shelf, gold_source, gold_phrase, kind
  gold_source  part of the book file name that holds the answer
  gold_phrase  6-10 consecutive words copied from the answering passage
  kind         free label; 'out_of_corpus' rows have no gold passage (only the best distance is shown)
Only retrieval is measured, so no chat model is needed.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from papermind.config import load_config  # noqa: E402
from papermind.embeddings import make_embedder  # noqa: E402
from papermind.retrieve import retrieve  # noqa: E402
from papermind.store import Store  # noqa: E402


def norm(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.lower()))


def hit_rank(passages, gold_source: str, gold_phrase: str) -> int | None:
    phrase = norm(gold_phrase)
    for rank, p in enumerate(passages, 1):
        if gold_source.lower() in p.source_file.lower() and phrase in norm(p.text):
            return rank
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--config")
    args = ap.parse_args()

    cfg = load_config(args.config)
    embedder = make_embedder(cfg)
    store = Store(cfg.chroma_path)

    ranks: list[int | None] = []
    by_kind: dict[str, list[int | None]] = {}
    with open(args.csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            col = store.open_shelf(row["shelf"], embedder)
            ps = retrieve(col, embedder, row["question"], k=args.k)
            if row.get("kind") == "out_of_corpus" or not row.get("gold_phrase"):
                best = ps[0].distance if ps else float("nan")
                print(f"[out-of-corpus] best distance {best:.3f}  {row['question'][:70]}")
                continue
            r = hit_rank(ps, row["gold_source"], row["gold_phrase"])
            ranks.append(r)
            by_kind.setdefault(row.get("kind", ""), []).append(r)
            print(f"[{'miss' if r is None else 'rank ' + str(r):>7}] {row['question'][:70]}")

    def summary(rs):
        n = len(rs) or 1
        at = lambda k: sum(1 for r in rs if r is not None and r <= k) / n
        mrr = sum(1 / r for r in rs if r) / n
        return f"n={len(rs)}  hit@1={at(1):.2f}  hit@3={at(3):.2f}  hit@{args.k}={at(args.k):.2f}  MRR={mrr:.2f}"

    print("\nALL     ", summary(ranks))
    for kind, rs in sorted(by_kind.items()):
        print(f"{kind or '-':8}", summary(rs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
