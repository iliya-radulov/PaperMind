"""Settings: defaults, overridden by ./papermind.toml, overridden by PAPERMIND_* env vars.

Every model name lives here so you can change models without touching code.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class Config:
    ollama_host: str = "http://localhost:11434"
    embed_model: str = "bge-m3"
    chat_model: str = "qwen2.5:14b"
    num_ctx: int = 16384          # Ollama defaults to 4096 and silently cuts long prompts
    temperature: float = 0.0
    chroma_path: str = "./chroma_db"
    books_dir: str = "./books"
    embedder: str = "ollama"      # "ollama" or "hash" (hash is for tests only)
    chunk_words: int = 280        # target words per chunk
    chunk_overlap_words: int = 40
    min_chapter_words: int = 120  # shorter sections are folded into the next one
    top_k: int = 6
    persona_top_k: int = 10       # abstract questions need more of the author's writing
    persona_temperature: float = 0.7  # voice needs some freedom; factual mode stays at 0
    host: str = "127.0.0.1"
    port: int = 5050


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg = Config()
    toml_path = Path(path or os.environ.get("PAPERMIND_CONFIG", "papermind.toml"))
    if toml_path.is_file():
        with toml_path.open("rb") as fh:
            data = tomllib.load(fh)
        for f in fields(cfg):
            if f.name in data:
                setattr(cfg, f.name, type(getattr(cfg, f.name))(data[f.name]))
    for f in fields(cfg):
        env = os.environ.get(f"PAPERMIND_{f.name.upper()}")
        if env is not None:
            setattr(cfg, f.name, type(getattr(cfg, f.name))(env))
    return cfg
