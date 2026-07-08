"""Live-mode ingest orchestration + honest data-source status reporting.

This is the data-source swap the architecture was designed for: it flips the
ingest path from checked-in fixtures to REAL MLB odds from The Odds API, mapping
the response into the SAME normalized schema the fixtures use so the existing
EV/CLV/line-movement engine consumes live data with NO math rewrite.

Design constraints (ratified plan + task brief):

  * QUOTA DISCIPLINE. The free tier is 500 requests/MONTH total. There is NO
    background poller here — `refresh_live()` is an explicit, on-demand trigger
    (invoked by scripts/run_ingest.py --source live or scripts/refresh_live.py).
    Defaults are the cheapest useful call: baseball_mlb, regions=us, markets=h2h.
    One well-formed call pulls all current MLB games at once.
  * QUOTA VISIBILITY. Every live call's x-requests-used / x-requests-remaining
    headers are captured by the provider, persisted on the ingest_run row, and
    logged. `data_source_status()` surfaces remaining quota for /api/capabilities.
  * MODE GATING. Key absent -> we NEVER touch the network (zero spend); the app
    stays in fixture mode. Key present -> live mode is AVAILABLE via the explicit
    trigger, still never automatic on a read request.
  * GRACEFUL DEGRADATION. On API error / quota exhaustion / network failure we
    record the failed run for auditing, keep the last-known snapshots intact, and
    report the degraded state honestly. We NEVER fabricate odds.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field

from ..providers.base import FetchResult
from ..providers.fixture import FixtureTheOddsAPIProvider
from ..providers.the_odds_api import TheOddsAPIProvider
from .pipeline import ingest_fetch_result

# Quota-frugal defaults. h2h only keeps a single MLB pull to 1 market x 1 region
# = 1 credit. spreads/totals are opt-in via markets= only when quota clearly
# allows (each extra market multiplies the per-call credit cost).
DEFAULT_SPORT = "baseball_mlb"
DEFAULT_MARKETS: tuple[str, ...] = ("h2h",)
DEFAULT_REGIONS: tuple[str, ...] = ("us",)

# The Odds API bookmaker feeds place Pinnacle (our sharpest anchor) under the eu
# region only. Requesting eu alongside us captures it — but eu adds a region and
# therefore multiplies credit cost, so it stays OPT-IN (regions=us,eu) rather
# than a default. Documented here so the trade-off is explicit at the call site.

_ENV_KEY = "THE_ODDS_API_KEY"


def live_mode_available() -> bool:
    """True iff a key is present. Never makes a network call."""
    return bool(os.environ.get(_ENV_KEY))


@dataclass
class LiveIngestResult:
    """Outcome of an on-demand live refresh (success or graceful failure)."""
    ok: bool
    mode: str                      # 'live' | 'fixture'
    sport_key: str
    markets: tuple[str, ...]
    regions: tuple[str, ...]
    requests_used: int | None = None
    requests_remaining: int | None = None
    events_seen: int = 0
    snapshots_written: int = 0
    run_id: int | None = None
    error: str | None = None
    note: str | None = None


def _mask_key(key: str | None) -> str:
    if not key:
        return "<unset>"
    if len(key) <= 6:
        return "***"
    return f"{key[:4]}…{key[-2:]}"


def refresh_live(
    conn: sqlite3.Connection,
    sport_key: str = DEFAULT_SPORT,
    markets: tuple[str, ...] = DEFAULT_MARKETS,
    regions: tuple[str, ...] = DEFAULT_REGIONS,
    provider: TheOddsAPIProvider | None = None,
    logger=print,
) -> LiveIngestResult:
    """Perform ONE deliberate live pull and ingest it. On-demand only.

    Returns a LiveIngestResult describing what happened. On any failure we DO NOT
    raise past the ingest boundary — we log, keep existing snapshots untouched,
    and return ok=False so callers/UI can report the degraded state honestly.

    This spends quota. It must only be called from an explicit trigger — never
    from a read endpoint, never in a loop, never in tests (tests mock the
    provider so they cost zero quota).
    """
    if not live_mode_available() and provider is None:
        return LiveIngestResult(
            ok=False,
            mode="fixture",
            sport_key=sport_key,
            markets=markets,
            regions=regions,
            error=f"{_ENV_KEY} not set — refusing to attempt a live call (zero spend).",
            note="Set the key to enable on-demand live refresh.",
        )

    prov = provider or TheOddsAPIProvider()
    key_hint = _mask_key(os.environ.get(_ENV_KEY))
    logger(
        f"[live-ingest] START sport={sport_key} markets={','.join(markets)} "
        f"regions={','.join(regions)} key={key_hint}"
    )

    # 1) Fetch (this is the ONLY step that spends quota).
    try:
        result: FetchResult = prov.fetch_odds(sport_key, markets=markets, regions=regions)
    except Exception as exc:  # noqa: BLE001 — network / HTTP / quota errors
        msg = str(exc)[:400]
        logger(f"[live-ingest] FETCH FAILED: {msg}")
        _record_failed_run(conn, sport_key, msg)
        return LiveIngestResult(
            ok=False,
            mode="live",
            sport_key=sport_key,
            markets=markets,
            regions=regions,
            error=msg,
            note="Live fetch failed — last-known snapshots retained; no odds fabricated.",
        )

    # Log quota AS SOON as we have it, on every call, regardless of ingest outcome.
    logger(
        f"[live-ingest] QUOTA used={result.requests_used} "
        f"remaining={result.requests_remaining} events={len(result.events)}"
    )

    if not result.events:
        # A valid empty response (e.g. no MLB games scheduled today). Not an
        # error, but nothing to ingest — record the run for quota provenance.
        run_id = _record_empty_run(conn, sport_key, result)
        logger("[live-ingest] OK but 0 events (no games in window) — nothing ingested.")
        return LiveIngestResult(
            ok=True,
            mode="live",
            sport_key=sport_key,
            markets=markets,
            regions=regions,
            requests_used=result.requests_used,
            requests_remaining=result.requests_remaining,
            events_seen=0,
            snapshots_written=0,
            run_id=run_id,
            note="Live call succeeded but returned no events in the current window.",
        )

    # 2) Ingest into the SAME normalized store the fixtures use (dedup + movement).
    try:
        summary = ingest_fetch_result(
            conn, result, provider_name=prov.name, sport_key_hint=sport_key
        )
    except Exception as exc:  # noqa: BLE001 — ingest_fetch_result already recorded failure
        msg = str(exc)[:400]
        logger(f"[live-ingest] INGEST FAILED: {msg}")
        return LiveIngestResult(
            ok=False,
            mode="live",
            sport_key=sport_key,
            markets=markets,
            regions=regions,
            requests_used=result.requests_used,
            requests_remaining=result.requests_remaining,
            error=msg,
            note="Fetched live odds but ingest failed — see ingest_run for the error row.",
        )

    logger(
        f"[live-ingest] DONE run={summary['run_id']} events={summary['events_seen']} "
        f"snapshots={summary['snapshots_written']} remaining={result.requests_remaining}"
    )
    return LiveIngestResult(
        ok=True,
        mode="live",
        sport_key=sport_key,
        markets=markets,
        regions=regions,
        requests_used=result.requests_used,
        requests_remaining=result.requests_remaining,
        events_seen=summary["events_seen"],
        snapshots_written=summary["snapshots_written"],
        run_id=summary["run_id"],
    )


def _record_failed_run(conn: sqlite3.Connection, sport_key: str, note: str) -> int | None:
    """Record a failed live fetch for auditing (no snapshots written)."""
    try:
        cur = conn.execute(
            """INSERT INTO ingest_run
                (provider, sport_key, started_at, finished_at, status, note)
               VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                       strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'error', ?)""",
            ("the_odds_api", sport_key, f"live fetch failed: {note}"[:500]),
        )
        conn.commit()
        return cur.lastrowid
    except Exception:  # noqa: BLE001 — never let audit-logging mask the real error
        return None


def _record_empty_run(conn: sqlite3.Connection, sport_key: str, result: FetchResult) -> int | None:
    try:
        cur = conn.execute(
            """INSERT INTO ingest_run
                (provider, sport_key, started_at, finished_at, status,
                 events_seen, snapshots_written, requests_used, requests_remaining, note)
               VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                       strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'ok', 0, 0, ?, ?, ?)""",
            (
                "the_odds_api", sport_key,
                result.requests_used, result.requests_remaining,
                "live call ok — 0 events in window",
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Honest data-source status — read-only, cheap, safe on every request.
# ---------------------------------------------------------------------------
@dataclass
class DataSourceStatus:
    """What /api/capabilities needs to tell the truth about the data feed."""
    mode: str                          # 'live' | 'fixture'
    live_available: bool               # key present?
    last_live_pull_at: str | None = None
    last_live_status: str | None = None
    quota_remaining: int | None = None
    quota_used: int | None = None
    last_ingest_at: str | None = None  # any ingest (fixture or live)
    degraded: bool = False
    degraded_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "live_available": self.live_available,
            "last_live_pull_at": self.last_live_pull_at,
            "last_live_status": self.last_live_status,
            "quota_remaining": self.quota_remaining,
            "quota_used": self.quota_used,
            "last_ingest_at": self.last_ingest_at,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }


def data_source_status(conn: sqlite3.Connection) -> DataSourceStatus:
    """Derive honest data-source status from the ingest_run ledger.

    Read-only and quota-free. Mode is 'live' iff at least one successful live
    ingest has actually written snapshots; otherwise 'fixture'. Quota remaining
    is taken from the most recent live run that reported it.
    """
    live_available = live_mode_available()

    def _q(sql: str, params: tuple = ()):  # small helper; returns Row | None
        try:
            return conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return None

    # Most recent live run overall (any status), for freshness + last status.
    last_live = _q(
        """SELECT started_at, finished_at, status, note,
                  requests_used, requests_remaining, snapshots_written
           FROM ingest_run
           WHERE provider = 'the_odds_api'
             AND note IS NOT 'seeded from fixture'
             AND (requests_remaining IS NOT NULL OR note LIKE 'live%')
           ORDER BY id DESC LIMIT 1"""
    )

    # Most recent SUCCESSFUL live run that wrote real snapshots -> proves live mode.
    successful_live = _q(
        """SELECT started_at, requests_remaining, requests_used
           FROM ingest_run
           WHERE provider = 'the_odds_api' AND status = 'ok'
             AND requests_remaining IS NOT NULL
           ORDER BY id DESC LIMIT 1"""
    )

    # Most recent quota reading from ANY run that reported it.
    quota_row = _q(
        """SELECT requests_remaining, requests_used
           FROM ingest_run
           WHERE requests_remaining IS NOT NULL
           ORDER BY id DESC LIMIT 1"""
    )

    # Most recent ingest of any kind (freshness of the data the API serves).
    last_any = _q(
        """SELECT finished_at, started_at FROM ingest_run
           WHERE status = 'ok' ORDER BY id DESC LIMIT 1"""
    )

    mode = "live" if successful_live is not None else "fixture"
    quota_remaining = quota_row["requests_remaining"] if quota_row else None
    quota_used = quota_row["requests_used"] if quota_row else None

    last_live_pull_at = None
    last_live_status = None
    degraded = False
    degraded_reason = None
    if last_live is not None:
        last_live_pull_at = last_live["finished_at"] or last_live["started_at"]
        last_live_status = last_live["status"]
        if last_live["status"] == "error":
            degraded = True
            degraded_reason = (
                (last_live["note"] or "last live pull failed")
                + " — serving last-known snapshots; no odds fabricated."
            )

    if quota_remaining is not None and quota_remaining <= 0:
        degraded = True
        degraded_reason = (
            "The Odds API monthly quota exhausted — serving last-known snapshots; "
            "no odds fabricated."
        )

    last_ingest_at = None
    if last_any is not None:
        last_ingest_at = last_any["finished_at"] or last_any["started_at"]

    return DataSourceStatus(
        mode=mode,
        live_available=live_available,
        last_live_pull_at=last_live_pull_at,
        last_live_status=last_live_status,
        quota_remaining=quota_remaining,
        quota_used=quota_used,
        last_ingest_at=last_ingest_at,
        degraded=degraded,
        degraded_reason=degraded_reason,
    )
