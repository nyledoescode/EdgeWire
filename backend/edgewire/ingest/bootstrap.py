"""First-boot bootstrap: ensure the DB has schema + seed data.

Render (and any fresh deploy) starts with an EMPTY persistent disk, so the
SQLite file has no tables and no odds rows. Endpoints would return empty until
an ingest ran. This module makes the API self-seed on startup from the checked-in
MLB fixtures (no API key, no network, no spend) so the deployed endpoints return
real fixture data immediately (e.g. Red Sox +6.76% EV).

Seeding is idempotent and cheap:
  * init_db() applies schema.sql (all CREATE IF NOT EXISTS).
  * We only load fixtures when the odds store is empty, so restarts against a
    populated persistent disk are a no-op and never clobber accumulated history.

When THE_ODDS_API_KEY is later provisioned and live ingest runs, real snapshots
accumulate on the same disk; this bootstrap stays inert (DB no longer empty).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..db.database import init_db
from ..providers.base import FetchResult
from ..providers.the_odds_api import _parse_events
from .pipeline import ingest_fetch_result

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"

# MLB fixture snapshots to seed, in chronological order. The _t2 snapshot gives
# the frontend real line movement to render (opening -> later observation).
_SEED_FIXTURES = [
    ("baseball_mlb", "the_odds_api_baseball_mlb.json"),
    ("baseball_mlb", "the_odds_api_baseball_mlb_t2.json"),
]

_DEFAULT_MARKETS = ("h2h", "spreads", "totals")


def _odds_row_count(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM odds_snapshot").fetchone()
    except sqlite3.OperationalError:
        # Table doesn't exist yet -> definitely empty.
        return 0
    return int(row["n"] if isinstance(row, sqlite3.Row) else row[0])


def _load_fixture(path: Path) -> FetchResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return FetchResult(events=_parse_events(payload))


def seed_if_empty(conn: sqlite3.Connection, fixture_dir: Path | None = None) -> dict:
    """Apply schema, then load MLB fixtures iff the odds store is empty.

    Returns a small summary dict describing what happened. Safe to call on every
    boot: it never re-seeds a non-empty DB.
    """
    init_db(conn)

    if _odds_row_count(conn) > 0:
        return {"seeded": False, "reason": "db already populated"}

    fixture_dir = fixture_dir or _FIXTURE_DIR
    loaded = []
    for sport_key, filename in _SEED_FIXTURES:
        fpath = fixture_dir / filename
        if not fpath.exists():
            continue
        result = _load_fixture(fpath)
        summary = ingest_fetch_result(
            conn, result, provider_name="the_odds_api", sport_key_hint=sport_key
        )
        loaded.append({"fixture": filename, "summary": summary})

    return {"seeded": True, "fixtures": loaded, "odds_rows": _odds_row_count(conn)}
