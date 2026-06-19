"""SQLite access layer for the EdgeWire odds store.

Stdlib-only (sqlite3) to keep the footprint tiny. The connection helpers here
are the single chokepoint for all reads/writes so we can later port to Postgres
by swapping this module without touching ingestion or provider code.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Default DB location; override with EDGEWIRE_DB env var.
_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "edgewire.db"
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def db_path() -> Path:
    return Path(os.environ.get("EDGEWIRE_DB", str(_DEFAULT_DB)))


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Open a connection with sane pragmas and Row access by column name."""
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Apply schema.sql (idempotent — all CREATE statements use IF NOT EXISTS)."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def reset_db(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Drop the DB file and recreate from schema. Used by tests / fresh setups."""
    target = Path(path) if path is not None else db_path()
    if target.exists():
        target.unlink()
    conn = connect(target)
    init_db(conn)
    return conn
