"""Answer generation with Ollama. Answers only from the retrieved passages, with citations."""
from __future__ import annotations

import requests

from .config import Config
from .personas import Persona
from .retrieve import Passage

PROMPT = """You are a careful reading companion for works of fiction.
Answer the question using ONLY the numbered passages below.
- Cite the passages you use like [1], [2].
- If the passages do not contain enough information, say so plainly. Do not use outside knowledge
  about the books and do not invent plot details, quotes or names.
- Answer in the language of the question.

Passages:
{context}

Question: {question}

Answer:"""


PERSONA_PROMPT = """You are writing a short piece in the manner of {name}, as a literary exercise:
the answer the author might plausibly give to the question below, in their voice and from their
known outlook. It is a pastiche, not a real statement by the author.

Rules:
- The ideas, attitudes, images and recurring themes must come from the numbered passages, which are
  the author's own writing. Take the voice (diction, rhythm, humour, imagery) from them too.
- Style notes: {style}
- The question may be about something the books never mention. Then apply the author's outlook to
  it, but do not invent facts about the books or real events, and do not present any sentence as a
  real quotation unless it appears in the passages.
- Write in the first person, in the voice, with no preamble and no disclaimers inside the piece.
  Roughly 150-300 words unless the question needs more.
- Answer in the language of the question.
- After the piece write a line containing only --- and then "Grounding:" with one or two plain,
  out-of-character sentences: which passages [n] the ideas came from, and whether the question
  went beyond what the passages cover.

Passages:
{context}

Question: {question}

Piece:"""


def format_context(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{i}] {p.cite}\n{p.text}" for i, p in enumerate(passages, 1))


def build_prompt(question: str, passages: list[Passage], persona: Persona | None = None) -> str:
    if persona is not None:
        return PERSONA_PROMPT.format(
            name=persona.name,
            style=persona.style,
            context=format_context(passages),
            question=question,
        )
    return PROMPT.format(context=format_context(passages), question=question)


def generate(
    cfg: Config, question: str, passages: list[Passage], persona: Persona | None = None
) -> dict:
    """Returns {'answer', 'prompt_tokens', 'truncated'}. 'truncated' is True when the prompt came
    close to the context window, i.e. the start of it (instructions, best passage) may be cut."""
    if not passages:
        return {
            "answer": "No passages were found for this question.",
            "prompt_tokens": 0,
            "truncated": False,
        }
    payload = {
        "model": cfg.chat_model,
        "messages": [{"role": "user", "content": build_prompt(question, passages, persona)}],
        "stream": False,
        "options": {
            "temperature": cfg.persona_temperature if persona else cfg.temperature,
            "num_ctx": cfg.num_ctx,
        },
    }
    try:
        resp = requests.post(f"{cfg.ollama_host.rstrip('/')}/api/chat", json=payload, timeout=600)
    except requests.RequestException as exc:
        raise RuntimeError(f"Cannot reach Ollama at {cfg.ollama_host}: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama chat failed ({resp.status_code}): {resp.text[:200]}. "
            f"Is the model pulled? Try: ollama pull {cfg.chat_model}"
        )
    data = resp.json()
    used = int(data.get("prompt_eval_count", 0))
    return {
        "answer": data["message"]["content"].strip(),
        "prompt_tokens": used,
        "truncated": used >= int(cfg.num_ctx * 0.95),
    }
