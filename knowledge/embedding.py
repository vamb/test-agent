from __future__ import annotations

import hashlib
import math


class HashEmbeddingGenerator:
    """Local deterministic embedding generator for offline pgvector MVP tests."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        normalized_text = "".join(text.lower().split())
        if not normalized_text:
            return vector

        for token in self._tokens(normalized_text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        length = math.sqrt(sum(value * value for value in vector))
        if length == 0:
            return vector
        return [round(value / length, 6) for value in vector]

    def _tokens(self, text: str) -> list[str]:
        if len(text) <= 3:
            return [text]
        tokens = [text[index : index + 2] for index in range(len(text) - 1)]
        tokens.extend(text[index : index + 3] for index in range(len(text) - 2))
        return tokens


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"

