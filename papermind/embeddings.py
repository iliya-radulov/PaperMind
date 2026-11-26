"""Embedders. Production: Ollama (bge-m3). Tests: a deterministic hash embedder."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import requests

from .config import Config


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    def __init__(self, host: str, model: str, batch: int = 16):
        self.host = host.rstrip("/")
        self.model = model
        self.name = model
        self.batch = batch

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            try:
                resp = requests.post(
                    f"{self.host}/api/embed",
                    json={"model": self.model, "input": texts[i : i + self.batch]},
                    timeout=300,
                )
            except requests.RequestException as exc:
                raise RuntimeError(f"Cannot reach Ollama at {self.host}: {exc}") from exc
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama embed failed ({resp.status_code}): {resp.text[:200]}. "
                    f"Is Ollama running and is the model pulled? Try: ollama pull {self.model}"
                )
            out.extend(resp.json()["embeddings"])
        return out


class HashEmbedder:
    """Bag-of-words hashing into 256 dims. Not semantic; only for tests and offline smoke runs."""

    name = "hash-256"
    DIM = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            v = [0.0] * self.DIM
            for w in re.findall(r"\w+", t.lower()):
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                v[h % self.DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / norm for x in v])
        return vecs


def make_embedder(cfg: Config) -> Embedder:
    if cfg.embedder == "hash":
        return HashEmbedder()
    return OllamaEmbedder(cfg.ollama_host, cfg.embed_model)
