"""Screen assemblers: turn stored odds + the intelligence engine into the
response shapes the frontend consumes (API_CONTRACT.md / src/types.ts).

`build_ev_screen` produces EvScreenResponse: events -> markets -> outcomes, each
outcome carrying server-computed fairProb/fairPrice (Spec 01 consensus), bestPrice
line-shopping, leave-one-out EV, per-book prices, and a movement sparkline.

`build_clv_summary` produces ClvSummary from the bet_signal ledger via the CLV
aggregation (Spec 02) — with mandatory confidence intervals + display gate.

Pure-ish: takes a sqlite connection, returns plain dicts (JSON-serializable).
EV math is delegated to edgewire.intelligence; CLV to edgewire.clv.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import intelligence as iq
from . import clv as clvm
from .odds_math import american_to_decimal

# Spec 01 §4.3 threshold by market class (mainlines here).
_MARKET_THRESHOLD = {"h2h": "mainline", "spreads": "mainline", "totals": "mainline"}
_MARKET_LABEL = {"h2h": "Moneyline", "spreads": "Spread", "totals": "Total"}

# Sport_key -> frontend Sport enum.
_SPORT_ENUM = {
    "baseball_mlb": "MLB",
    "americanfootball_nfl": "NFL",
    "basketball_nba": "NBA",
    "icehockey_nhl": "NHL",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _latest_rows(conn, event_id, market_key):
    """Latest price per (book, selection, point) for a market, with book meta."""
    return conn.execute(
        """
        SELECT b.book_key, b.title AS book_title, b.is_sharp,
               v.selection, v.point, v.price_american, v.book_last_update,
               v.observed_at
        FROM v_latest_odds v
        JOIN bookmaker b ON b.id = v.bookmaker_id
        JOIN market_type m ON m.id = v.market_type_id
        WHERE v.event_id = ? AND m.market_key = ?
        ORDER BY v.selection, v.price_american DESC
        """,
        (event_id, market_key),
    ).fetchall()


def _movement_series(conn, event_id, market_key, book_key, selection):
    rows = conn.execute(
        """
        SELECT s.observed_at, s.price_american, s.point
        FROM odds_snapshot s
        JOIN bookmaker b ON b.id = s.bookmaker_id
        JOIN market_type m ON m.id = s.market_type_id
        WHERE s.event_id = ? AND m.market_key = ? AND b.book_key = ? AND s.selection = ?
        ORDER BY s.observed_at
        """,
        (event_id, market_key, book_key, selection),
    ).fetchall()
    return [{"t": r["observed_at"], "price": r["price_american"], "point": r["point"]} for r in rows]


def _build_market(conn, event_id, market_key, tau=None):
    """Assemble one market's outcomes with consensus fair value + EV."""
    rows = _latest_rows(conn, event_id, market_key)
    if not rows:
        return None

    # Group latest quotes by selection (for totals/spreads, also by point).
    by_selection: dict[str, list] = {}
    for r in rows:
        by_selection.setdefault(r["selection"], []).append(r)

    selections = list(by_selection.keys())
    if len(selections) < 2:
        return None  # need a complete market to de-vig (Spec 01 §6.7)

    # Build BookQuotes: for each book that quotes BOTH sides, pair them so we can
    # de-vig within the book. We index selection order consistently.
    sel_index = {s: i for i, s in enumerate(selections)}

    # Collect, per book, the American price for each selection (latest).
    book_prices: dict[str, dict[str, dict]] = {}
    for r in rows:
        book_prices.setdefault(r["book_key"], {})[r["selection"]] = r

    # Per-selection consensus across books.
    outcomes = []
    # Pre-build quote lists per selection for consensus().
    def quotes_for(selection_idx: int) -> list[iq.BookQuote]:
        qs = []
        now = datetime.now(timezone.utc)
        for book_key, sels in book_prices.items():
            if not all(s in sels for s in selections):
                continue  # book must quote the full market to de-vig
            market_american = [int(sels[s]["price_american"]) for s in selections]
            age = None
            lu = sels[selections[selection_idx]]["book_last_update"]
            if lu:
                try:
                    ts = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                    age = (now - ts).total_seconds()
                except ValueError:
                    age = None
            qs.append(iq.BookQuote(
                book_key=book_key,
                market_american=market_american,
                outcome_index=selection_idx,
                age_seconds=age,
                is_sharp=bool(sels[selections[selection_idx]]["is_sharp"]),
            ))
        return qs

    # Compute consensus per selection, then renormalize across the market.
    cons = []
    for i in range(len(selections)):
        qs = quotes_for(i)
        cons.append(iq.consensus(qs, tau=tau) if qs else None)

    valid = [c for c in cons if c is not None]
    norm = iq.renormalize(valid) if len(valid) == len(cons) and valid else None

    threshold_class = _MARKET_THRESHOLD.get(market_key, "mainline")
    threshold = iq.EV_THRESHOLD[threshold_class]

    for i, selection in enumerate(selections):
        sel_rows = by_selection[selection]
        # best price (highest American) across books
        best = max(sel_rows, key=lambda r: r["price_american"])
        fair_prob = norm[i] if norm else (cons[i].fair_prob if cons[i] else None)
        confidence = cons[i].confidence if cons[i] else "low"

        prices = [
            {
                "book": r["book_key"],
                "bookName": r["book_title"],
                "price": r["price_american"],
                "point": r["point"],
                "updatedAt": r["book_last_update"] or r["observed_at"],
                "isBest": r["book_key"] == best["book_key"],
            }
            for r in sel_rows
        ]

        ev_frac = None
        is_plus = False
        if fair_prob is not None:
            # Grade the BEST offered price using a leave-one-out consensus (§4.5).
            loo = iq.leave_one_out_prob(quotes_for(i), best["book_key"], tau=tau)
            ref = loo.fair_prob if loo.n_books >= 1 else fair_prob
            ev_pct = iq.ev_pct(ref, american_to_decimal(best["price_american"]))
            ev_frac = round(ev_pct / 100.0, 4)
            is_plus = iq.is_plus_ev(ev_pct, confidence, stale=False, threshold=threshold)

        outcomes.append({
            "name": selection,
            "fairProb": round(fair_prob, 4) if fair_prob is not None else None,
            "fairPrice": iq.prob_to_american(fair_prob) if fair_prob else None,
            "bestPrice": best["price_american"],
            "bestBook": best["book_key"],
            "ev": ev_frac,
            "prices": prices,
            "movement": _movement_series(conn, event_id, market_key, best["book_key"], selection),
            # additive intelligence fields (FE may ignore until ready)
            "confidence": confidence,
            "isPlusEv": is_plus,
            "stale": False,
        })

    return {"type": market_key, "label": _MARKET_LABEL.get(market_key, market_key), "outcomes": outcomes}


def build_ev_screen(conn: sqlite3.Connection, sport_key: str | None = None,
                    markets: tuple[str, ...] = ("h2h", "spreads", "totals")) -> dict:
    """Assemble the EvScreenResponse (API_CONTRACT.md)."""
    q = """
        SELECT e.id, e.provider_event_id, s.sport_key, s.title AS sport_title,
               e.commence_time, e.home_team, e.away_team
        FROM event e JOIN sport s ON s.id = e.sport_id
    """
    params: tuple = ()
    if sport_key:
        q += " WHERE s.sport_key = ?"
        params = (sport_key,)
    q += " ORDER BY e.commence_time"

    events = []
    for ev in conn.execute(q, params).fetchall():
        mkts = []
        for mk in markets:
            built = _build_market(conn, ev["id"], mk)
            if built:
                mkts.append(built)
        if not mkts:
            continue
        events.append({
            "id": ev["provider_event_id"],
            "sport": _SPORT_ENUM.get(ev["sport_key"], ev["sport_key"]),
            "league": _SPORT_ENUM.get(ev["sport_key"], ev["sport_key"]),
            "startTime": ev["commence_time"],
            "homeTeam": ev["home_team"],
            "awayTeam": ev["away_team"],
            "markets": mkts,
        })

    return {"generatedAt": _utcnow(), "events": events}


def build_clv_summary(conn: sqlite3.Connection, window: str = "all") -> dict:
    """Assemble ClvSummary from the bet_signal ledger (Spec 02 aggregation).

    Honest-by-construction: aggregates ALL graded bets (no cherry-picking),
    always returns sample size + CIs + display gate.
    """
    rows = conn.execute(
        """
        SELECT bs.*, e.home_team, e.away_team
        FROM bet_signal bs
        JOIN event e ON e.id = bs.event_id
        WHERE bs.clv_status = 'graded'
        ORDER BY bs.logged_at_utc DESC
        """
    ).fetchall()

    grades = [
        clvm.ClvGrade(
            clv_prob=r["clv_prob"],
            beat_close=r["beat_close"],
            clv_pct=r["clv_pct"],
            clv_cents=r["clv_cents"],
        )
        for r in rows
        if r["clv_pct"] is not None
    ]
    agg = clvm.aggregate(grades)

    records = [
        {
            "id": r["bet_id"],
            "placedAt": r["logged_at_utc"],
            "sport": _SPORT_ENUM.get(r["sport_key"], r["sport_key"]),
            "event": f'{r["away_team"]} @ {r["home_team"]}',
            "market": r["market_key"],
            "selection": r["outcome"],
            "takenPrice": r["bet_american"],
            "closingPrice": r["closing_fair_american"],
            "clvPct": round(r["clv_pct"], 2) if r["clv_pct"] is not None else None,
            "result": "pending",  # settlement tracked separately
        }
        for r in rows
    ]

    return {
        "sampleSize": agg.n,
        "beatRate": round(agg.btc_rate, 4),
        "beatRateCI95": [round(agg.btc_ci95[0], 4), round(agg.btc_ci95[1], 4)],
        "avgClvPct": round(agg.avg_clv_pct, 3),
        "avgClvPctCI95": [round(agg.avg_clv_pct_ci95[0], 3), round(agg.avg_clv_pct_ci95[1], 3)],
        "medianClvPct": round(agg.median_clv_pct, 3),
        "displayGate": agg.display_gate,
        "window": window,
        "generatedAt": _utcnow(),
        "records": records,
    }
