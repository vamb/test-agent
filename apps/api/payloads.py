from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def payload_to_dict(payload: BaseModel | dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, BaseModel):
        return payload.model_dump()
    return payload
