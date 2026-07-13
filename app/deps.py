"""Shared FastAPI dependencies (pagination, future auth helpers)."""

from fastapi import Query


def pagination(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset
