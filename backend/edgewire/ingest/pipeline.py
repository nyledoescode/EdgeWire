"""Ingestion: normalize provider records into the time-series odds store.

Core responsibilities:
  * Upsert dimension rows (sport, bookmaker, market_type, event).
  * Append odds_snapshot rows, but ONLY when the (price, point) for a
    (event, book, market, selection) key differs from the most recent
    observation — this keeps the time series compact while preserving every
    genuine line move (needed for movement charts + CLV).
  * Flag the first-ever observation of each selection key as `is_opening`.
  * Record an ingest_run row for provenance/auditing.

No EV/fair-value math here — this layer only lands raw normalized market data.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..odds_math import american_to_decimal
from ..providers.base import FetchResult, NormalizedEvent
from ..providers.the_odds_api import SHARP_BOOKS, SHARP_BOOK_REGION

# Market metadata: which markets carry a line (point).
_MARKET_HAS_LINE = {
    "h2h": (False, "Moneyline"),
    "spreads": (True, "Point Spread"),
    "totals": (True, "Over/Under"),
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _get_or_create_sport(conn, sport_key: str, title: str) -> int:
    row = conn.execute("SELECT id FROM sport WHERE sport_key = ?", (sport_key,)).fetchone()
    if row:
        return row["id"]
    group = title.split()[0] if title else None
    cur = conn.execute(
        'INSERT INTO sport (sport_key, title, "group") VALUES (?, ?, ?)',
        (sport_key, title, group),
    )
    return cur.lastrowid


def _get_or_create_bookmaker(conn, book_key: str, title: str) -> int:
    row = conn.execute("SELECT id FROM bookmaker WHERE book_key = ?", (book_key,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO bookmaker (book_key, title, region, is_sharp) VALUES (?, ?, ?, ?)",
        (book_key, title, SHARP_BOOK_REGION.get(book_key), 1 if book_key in SHARP_BOOKS else 0),
    )
    return cur.lastrowid


def _get_or_create_market_type(conn, market_key: str) -> int:
    row = conn.execute(
        "SELECT id FROM market_type WHERE market_key = ?", (market_key,)
    ).fetchone()
    if row:
        return row["id"]
    has_line, title = _MARKET_HAS_LINE.get(market_key, (False, market_key))
    cur = conn.execute(
        "INSERT INTO market_type (market_key, title, has_line) VALUES (?, ?, ?)",
        (market_key, title, 1 if has_line else 0),
    )
    return cur.lastrowid


def _upsert_event(conn, ev: NormalizedEvent, sport_id: int, now: str) -> int:
    row = conn.execute(
        "SELECT id FROM event WHERE provider = ? AND provider_event_id = ?",
        (ev.provider, ev.provider_event_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE event SET last_seen_at = ?, commence_time = ? WHERE id = ?",
            (now, ev.commence_time, row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        """INSERT INTO event
            (provider, provider_event_id, sport_id, commence_time,
             home_team, away_team, first_seen_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ev.provider, ev.provider_event_id, sport_id, ev.commence_time,
            ev.home_team, ev.away_team, now, now,
        ),
    )
    return cur.lastrowid


def _latest_snapshot(conn, event_id, book_id, market_id, selection):
    return conn.execute(
        """SELECT price_american, point FROM odds_snapshot
           WHERE event_id = ? AND bookmaker_id = ? AND market_type_id = ?
                 AND selection = ?
           ORDER BY observed_at DESC, id DESC LIMIT 1""",
        (event_id, book_id, market_id, selection),
    ).fetchone()


def _selection_exists(conn, event_id, book_id, market_id, selection) -> bool:
    row = conn.execute(
        """SELECT 1 FROM odds_snapshot
           WHERE event_id = ? AND bookmaker_id = ? AND market_type_id = ?
                 AND selection = ? LIMIT 1""",
        (event_id, book_id, market_id, selection),
    ).fetchone()
    return row is not None


def ingest_fetch_result(
    conn: sqlite3.Connection,
    result: FetchResult,
    provider_name: str,
    sport_key_hint: str | None = None,
    observed_at: str | None = None,
) -> dict:
    """Persist a FetchResult. Returns summary counts. Commits on success."""
    now = observed_at or _utcnow_iso()

    run = conn.execute(
        """INSERT INTO ingest_run
            (provider, sport_key, started_at, status, requests_used, requests_remaining)
           VALUES (?, ?, ?, 'running', ?, ?)""",
        (provider_name, sport_key_hint, now, result.requests_used, result.requests_remaining),
    )
    run_id = run.lastrowid

    snapshots_written = 0
    events_seen = 0

    try:
        for ev in result.events:
            events_seen += 1
            sport_id = _get_or_create_sport(conn, ev.sport_key, ev.sport_title)
            event_id = _upsert_event(conn, ev, sport_id, now)

            for book in ev.books:
                book_id = _get_or_create_bookmaker(conn, book.book_key, book.title)
                for market in book.markets:
                    market_id = _get_or_create_market_type(conn, market.market_key)
                    for oc in market.outcomes:
                        prev = _latest_snapshot(
                            conn, event_id, book_id, market_id, oc.selection
                        )
                        # Dedup: skip if price AND point unchanged from last obs.
                        if prev is not None and (
                            prev["price_american"] == oc.price_american
                            and (prev["point"] == oc.point)
                        ):
                            continue
                        is_opening = 0 if _selection_exists(
                            conn, event_id, book_id, market_id, oc.selection
                        ) else 1
                        conn.execute(
                            """INSERT INTO odds_snapshot
                                (event_id, bookmaker_id, market_type_id, selection,
                                 description, point, price_american, price_decimal,
                                 book_last_update, observed_at, is_opening, ingest_run_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                event_id, book_id, market_id, oc.selection,
                                oc.description, oc.point, oc.price_american,
                                american_to_decimal(oc.price_american),
                                market.book_last_update, now, is_opening, run_id,
                            ),
                        )
                        snapshots_written += 1

        conn.execute(
            """UPDATE ingest_run
               SET finished_at = ?, status = 'ok',
                   events_seen = ?, snapshots_written = ?
               WHERE id = ?""",
            (_utcnow_iso(), events_seen, snapshots_written, run_id),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - record failure for auditing
        conn.execute(
            "UPDATE ingest_run SET finished_at = ?, status = 'error', note = ? WHERE id = ?",
            (_utcnow_iso(), str(exc)[:500], run_id),
        )
        conn.commit()
        raise

    return {
        "run_id": run_id,
        "events_seen": events_seen,
        "snapshots_written": snapshots_written,
    }
