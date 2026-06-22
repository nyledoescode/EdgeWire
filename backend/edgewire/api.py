"""Read-side query helpers — the shared backend->frontend data contract.

These functions return plain dicts (JSON-serializable) that the Fullstack
Engineer's web app and the alert system consume. They expose ONLY raw market
data + line shopping + movement so far. EV/CLV fields are added here once the
quant's spec-driven compute module exists; the shapes below reserve space for
them (documented in docs/API_CONTRACT.md) without inventing numbers now.
"""
from __future__ import annotations

import sqlite3


def list_events(conn: sqlite3.Connection, sport_key: str | None = None) -> list[dict]:
    """Upcoming events, optionally filtered by sport."""
    q = """
        SELECT e.id, e.provider_event_id, s.sport_key, s.title AS sport_title,
               e.commence_time, e.home_team, e.away_team, e.status
        FROM event e JOIN sport s ON s.id = e.sport_id
    """
    params: tuple = ()
    if sport_key:
        q += " WHERE s.sport_key = ?"
        params = (sport_key,)
    q += " ORDER BY e.commence_time"
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def line_shop(conn: sqlite3.Connection, event_id: int, market_key: str) -> list[dict]:
    """Best-available price per selection across books (line shopping).

    Returns latest price for every (book, selection) in the market, sorted so
    the best price for each selection is easy to surface in the UI.
    """
    rows = conn.execute(
        """
        SELECT b.book_key, b.title AS book_title, b.is_sharp,
               v.selection, v.point, v.price_american, v.price_decimal,
               v.observed_at
        FROM v_latest_odds v
        JOIN bookmaker b ON b.id = v.bookmaker_id
        JOIN market_type m ON m.id = v.market_type_id
        WHERE v.event_id = ? AND m.market_key = ?
        ORDER BY v.selection, v.price_american DESC
        """,
        (event_id, market_key),
    ).fetchall()
    return [dict(r) for r in rows]


def movement(
    conn: sqlite3.Connection,
    event_id: int,
    market_key: str,
    book_key: str,
    selection: str,
) -> list[dict]:
    """Full observed price history for one selection at one book (line chart)."""
    rows = conn.execute(
        """
        SELECT s.price_american, s.price_decimal, s.point,
               s.is_opening, s.observed_at, s.book_last_update
        FROM odds_snapshot s
        JOIN event e ON e.id = s.event_id
        JOIN bookmaker b ON b.id = s.bookmaker_id
        JOIN market_type m ON m.id = s.market_type_id
        WHERE s.event_id = ? AND m.market_key = ?
              AND b.book_key = ? AND s.selection = ?
        ORDER BY s.observed_at
        """,
        (event_id, market_key, book_key, selection),
    ).fetchall()
    return [dict(r) for r in rows]
