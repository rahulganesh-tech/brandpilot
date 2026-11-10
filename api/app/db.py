from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None


def open_pool(url: str | None = None) -> None:
    global _pool
    if _pool is not None:
        return
    url = url or config.DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # prepare_threshold=None keeps us compatible with Supabase's transaction pooler.
    _pool = ConnectionPool(
        url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
        open=True,
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    if _pool is None:
        open_pool()
    assert _pool is not None
    with _pool.connection() as conn:
        yield conn
