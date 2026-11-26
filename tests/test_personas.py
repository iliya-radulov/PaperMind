from papermind.answer import build_prompt
from papermind.personas import find_persona, load_personas
from papermind.retrieve import Passage


def P(i):
    return Passage(f"text {i}", "Cat's Cradle", "Kurt Vonnegut", "en", "f.epub", "id", i, f"c{i}", 0.1)


def test_default_personas_match_author_name_variants():
    ps = load_personas("does-not-exist.toml")
    assert find_persona("Kurt Vonnegut", ps).name == "Kurt Vonnegut"
    assert find_persona("Vonnegut, Kurt", ps).name == "Kurt Vonnegut"
    assert find_persona("Пелевин Виктор", ps).name == "Виктор Пелевин"
    assert find_persona("Terry Pratchett", ps).name == "Terry Pratchett"


def test_unknown_author_gets_generic_persona():
    p = find_persona("Ursula K. Le Guin", load_personas("does-not-exist.toml"))
    assert p.name == "Ursula K. Le Guin" and "passages" in p.style


def test_user_file_overrides_default(tmp_path):
    f = tmp_path / "personas.toml"
    f.write_text('[[persona]]\nname = "Kurt Vonnegut"\nmatch = ["vonnegut"]\nstyle = "MY STYLE"\n', encoding="utf-8")
    assert find_persona("Kurt Vonnegut", load_personas(f)).style == "MY STYLE"


def test_persona_prompt_is_grounded_and_labelled_as_pastiche():
    persona = find_persona("Kurt Vonnegut", load_personas("none.toml"))
    prompt = build_prompt("What is time?", [P(1), P(2)], persona)
    assert "in the manner of Kurt Vonnegut" in prompt and "pastiche" in prompt
    assert "[1] Cat's Cradle" in prompt and "[2]" in prompt
    assert "Grounding:" in prompt and "do not present any sentence as a" in prompt
    assert persona.style in prompt
    # factual prompt is unchanged
    assert "ONLY the numbered passages" in build_prompt("q", [P(1)])


def test_unreachable_ollama_is_a_readable_error_not_a_crash(cfg, monkeypatch):
    import pytest

    from papermind.answer import generate
    from papermind.embeddings import OllamaEmbedder

    cfg.ollama_host = "http://127.0.0.1:9"  # nothing listens here
    with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
        generate(cfg, "q", [P(1)])
    with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
        OllamaEmbedder(cfg.ollama_host, "bge-m3").embed(["x"])
