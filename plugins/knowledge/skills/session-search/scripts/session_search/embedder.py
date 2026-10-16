from __future__ import annotations

import array
import hashlib
import math
import os
import re

DIM = 384
TOKEN_RE = re.compile(r"[a-z0-9_]+")


class HashEmbedder:
    # ponytail: hashed ngrams ≠ neural similarity; SESSION_SEARCH_EMBEDDER=fastembed when paraphrase quality matters
    name = "hash-ngram"
    dim = DIM

    def embed(self, text: str) -> bytes:
        vec = [0.0] * DIM
        for tok in _tokens(text):
            digest = hashlib.blake2b(tok.encode("utf-8", "ignore"), digest_size=8).digest()
            idx = int.from_bytes(digest[:2], "little") % DIM
            sign = 1.0 if digest[2] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        packed = array.array("f", (x / norm for x in vec))
        return packed.tobytes()


def get_embedder():
    kind = os.environ.get("SESSION_SEARCH_EMBEDDER", "hash").strip().lower()
    if kind in {"fastembed", "bge", "neural"}:
        try:
            from fastembed import TextEmbedding  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"fastembed unavailable: {exc}") from exc
        return _FastembedEmbedder(TextEmbedding(model_name="BAAI/bge-small-en-v1.5"))
    return HashEmbedder()


class _FastembedEmbedder:
    name = "fastembed:bge-small-en-v1.5"
    dim = 384

    def __init__(self, model) -> None:
        self.model = model

    def embed(self, text: str) -> bytes:
        vec = next(self.model.embed([text or ""]))
        packed = array.array("f", (float(x) for x in vec))
        return packed.tobytes()


def cosine(a: bytes, b: bytes) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va = array.array("f")
    vb = array.array("f")
    va.frombytes(a)
    vb.frombytes(b)
    return float(sum(x * y for x, y in zip(va, vb)))


def _tokens(text: str) -> list[str]:
    s = (text or "").lower()
    words = TOKEN_RE.findall(s)
    compact = re.sub(r"\s+", " ", s)
    grams = [compact[i : i + 3] for i in range(max(0, len(compact) - 2))]
    return words + grams
