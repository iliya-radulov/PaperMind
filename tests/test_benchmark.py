import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))

from run_benchmark import hit_rank  # noqa: E402

from papermind.retrieve import Passage


def P(src, text):
    return Passage(text, "t", "a", "en", src, "id", 1, "c", 0.1)


def test_hit_rank_matches_source_and_phrase():
    ps = [P("a.epub", "nothing here"), P("b_book.epub", "He said: The Unique   Phrase, indeed.")]
    assert hit_rank(ps, "b_book", "the unique phrase") == 2
    assert hit_rank(ps, "a.epub", "the unique phrase") is None
    assert hit_rank(ps, "zzz", "nothing here") is None
