"""CLV grading job (Spec 02 §4.3) — closing-snapshot builder + grader.

Operates on the stored odds time-series. For each ungraded bet on a started
event, builds the closing consensus (Spec 02 §1.2: in-window, non-suspended,
per-book latest -> Spec 01 §3 consensus), computes the CLV metrics (clv.py),
and writes the grading fields back to bet_signal (append-only: a regrade writes
a new versioned row, never overwrites).

This is a batch job (run after events start). Kept dependency-free and
fixture-runnable. Polling-cadence tightening near close (Spec 02 §1.4) belongs
in the ingestion scheduler, not here.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from . import intelligence as iq
from . import clv as clvm
from .odds_math import american_to_decimal

# Spec 02 §1.2 capture windows (minutes) by market class.
W_CAPTURE_MIN = {"h2h": 10, "spreads": 10, "totals": 10, "props": 20}


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _closing_quotes(conn, event_id, market_key, commence_time, w_min) -> list[iq.BookQuote]:
    """Per-book latest non-suspended quote within [t_event - W, t_event) (§1.2).

    Returns BookQuotes for the home/away (or over/under) pair so consensus() can
    de-vig within each book. selection ordering is stable by selection name.
    """
    t_event = _parse_iso(commence_time)
    window_start = t_event - timedelta(minutes=w_min)

    rows = conn.execute(
        """
        SELECT b.book_key, b.is_sharp, s.selection, s.point, s.price_american,
               s.observed_at, s.book_last_update, s.is_suspended
        FROM odds_snapshot s
        JOIN bookmaker b ON b.id = s.bookmaker_id
        JOIN market_type m ON m.id = s.market_type_id
        WHERE s.event_id = ? AND m.market_key = ? AND s.is_suspended = 0
        ORDER BY s.observed_at
        """,
        (event_id, market_key),
    ).fetchall()

    # Keep only in-window observations; take each book's LATEST in-window quote
    # per selection.
    selections = sorted({r["selection"] for r in rows})
    sel_index = {s: i for i, s in enumerate(selections)}
    # book -> selection -> latest in-window american
    latest: dict[str, dict[str, dict]] = {}
    for r in rows:
        obs = _parse_iso(r["observed_at"])
        # use book_last_update when present for the freshness gate (§1.2 rule 1)
        ref_ts = _parse_iso(r["book_last_update"]) if r["book_last_update"] else obs
        if not (window_start <= ref_ts < t_event):
            continue
        latest.setdefault(r["book_key"], {})[r["selection"]] = r

    return selections, sel_index, latest


def _consensus_close(conn, event_id, market_key, commence_time, selection):
    """Closing consensus fair prob for one selection (§1.2 -> Spec 01 §3)."""
    w_min = W_CAPTURE_MIN.get(market_key, 10)
    selections, sel_index, latest = _closing_quotes(
        conn, event_id, market_key, commence_time, w_min
    )
    if selection not in sel_index:
        return None, 0, "low"
    idx = sel_index[selection]

    quotes = []
    for book_key, sels in latest.items():
        if not all(s in sels for s in selections):
            continue  # need full market to de-vig
        market_american = [int(sels[s]["price_american"]) for s in selections]
        quotes.append(iq.BookQuote(
            book_key=book_key,
            market_american=market_american,
            outcome_index=idx,
            is_sharp=bool(sels[selections[idx]]["is_sharp"]),
        ))
    if len(quotes) < 2:
        return None, len(quotes), "low"

    res = iq.consensus(quotes)
    return res.fair_prob, res.n_books, res.confidence


def grade_event_bets(conn: sqlite3.Connection, event_id: int) -> int:
    """Grade all pending bets for one event. Returns count graded."""
    bets = conn.execute(
        "SELECT * FROM bet_signal WHERE event_id = ? AND clv_status = 'pending'",
        (event_id,),
    ).fetchall()
    if not bets:
        return 0

    ev = conn.execute("SELECT commence_time FROM event WHERE id = ?", (event_id,)).fetchone()
    if not ev:
        return 0
    commence = ev["commence_time"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    graded = 0
    for bet in bets:
        p_close, n_books, conf = _consensus_close(
            conn, event_id, bet["market_key"], commence, bet["outcome"]
        )
        if p_close is None or n_books < 2:
            conn.execute(
                "UPDATE bet_signal SET clv_status = 'ungraded_no_close', graded_at_utc = ? WHERE id = ?",
                (now, bet["id"]),
            )
            continue

        g = clvm.grade_clv(
            bet_decimal=bet["bet_decimal"],
            fair_prob_at_bet=bet["fair_prob_at_bet"],
            closing_fair_prob=p_close,
        )
        conn.execute(
            """UPDATE bet_signal SET
                 event_start_utc = ?, closing_consensus_fair_prob = ?,
                 closing_fair_american = ?, n_books_close = ?, close_confidence = ?,
                 clv_prob = ?, beat_close = ?, clv_pct = ?, clv_cents = ?,
                 clv_status = 'graded', devig_method = 'multiplicative', graded_at_utc = ?
               WHERE id = ?""",
            (
                commence, p_close, iq.prob_to_american(p_close), n_books, conf,
                g.clv_prob, g.beat_close, g.clv_pct, g.clv_cents, now, bet["id"],
            ),
        )
        graded += 1

    conn.commit()
    return graded


def grade_all(conn: sqlite3.Connection) -> int:
    """Grade pending bets across all events (batch). Returns total graded."""
    eids = [r["event_id"] for r in conn.execute(
        "SELECT DISTINCT event_id FROM bet_signal WHERE clv_status = 'pending'"
    ).fetchall()]
    return sum(grade_event_bets(conn, eid) for eid in eids)
