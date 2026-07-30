from __future__ import annotations


def normalize_pagination(limit: int, offset: int, max_limit: int = 200) -> tuple[int, int]:
    return max(1, min(limit, max_limit)), max(0, offset)
