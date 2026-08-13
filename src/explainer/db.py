"""Thin Postgres layer. Deliberately raw psycopg — no ORM.

The orchestrator's whole job is expressing exact SQL semantics (FOR UPDATE SKIP
LOCKED, upserts on hash keys). An ORM would be a layer to fight, not a layer
to use. See PRD §6.2.

Works against local Postgres or Supabase. For Supabase, use the *session pooler*
connection string (port 5432) rather than the transaction pooler — the worker
relies on SELECT ... FOR UPDATE SKIP LOCKED inside an explicit transaction, and
`prepare_threshold=None` below keeps things safe if you do end up on pgbouncer.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .config import REPO_ROOT, settings


def connect() -> psycopg.Connection:
    return psycopg.connect(
        settings().database_url,
        row_factory=dict_row,
        autocommit=False,
        prepare_threshold=None,
    )


@contextmanager
def tx() -> Iterator[psycopg.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(conn: psycopg.Connection, sql: str, params: Any = None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        return list(cur.fetchall())


def one(conn: psycopg.Connection, sql: str, params: Any = None) -> dict | None:
    rows = query(conn, sql, params)
    return rows[0] if rows else None


def execute(conn: psycopg.Connection, sql: str, params: Any = None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


# ------------------------------------------------------------------- migrations

def migrate() -> list[str]:
    """Apply every migrations/*.sql not yet recorded. Idempotent."""
    applied: list[str] = []
    mig_dir = REPO_ROOT / "migrations"
    files = sorted(p for p in mig_dir.glob("*.sql"))
    with tx() as conn:
        execute(conn, """
            create table if not exists schema_migrations (
                filename text primary key,
                applied_at timestamptz not null default now()
            )""")
        done = {r["filename"] for r in query(conn, "select filename from schema_migrations")}
    for f in files:
        if f.name in done:
            continue
        sql = f.read_text()
        with tx() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("insert into schema_migrations(filename) values (%s)", (f.name,))
        applied.append(f.name)
    return applied


def reset_schema() -> None:
    """Drop and recreate public. Destructive; used by tests and `verify`."""
    with tx() as conn:
        execute(conn, "drop schema public cascade; create schema public;")
    migrate()


def dsn_summary() -> str:
    url = settings().database_url
    if "@" in url:
        return url.split("@", 1)[1]
    return url


def migrations_dir() -> Path:
    return REPO_ROOT / "migrations"
