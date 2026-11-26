"""Answer generation with Ollama. Answers only from the retrieved passages, with citations."""
from __future__ import annotations

import requests

from .config import Config
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


def format_context(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{i}] {p.cite}\n{p.text}" for i, p in enumerate(passages, 1))


def build_prompt(question: str, passages: list[Passage]) -> str:
    return PROMPT.format(context=format_context(passages), question=question)


def generate(cfg: Config, question: str, passages: list[Passage]) -> dict:
    """Returns {'answer', 'prompt_tokens', 'truncated'}. 'truncated' is True when the prompt came
    close to the context window, i.e. the start of it (instructions, best passage) may be cut."""
    if not passages:
        return {
            "answer": "No passages were found for this question.",
            "prompt_tokens": 0,
            "truncated": False,
        }
    resp = requests.post(
        f"{cfg.ollama_host.rstrip('/')}/api/chat",
        json={
            "model": cfg.chat_model,
            "messages": [{"role": "user", "content": build_prompt(question, passages)}],
            "stream": False,
            "options": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx},
        },
        timeout=600,
    )
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
