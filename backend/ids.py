from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str = "") -> str:
    try:
        from ulid import ULID

        value = str(ULID())
    except Exception:
        value = uuid4().hex
    return f"{prefix}{value}" if prefix else value
