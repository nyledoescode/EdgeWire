#!/usr/bin/env python3
"""EdgeWire ingestion runner.

Usage:
  # Initialize the DB schema
  python -m scripts.run_ingest --init

  # Ingest from a fixture (no API key, no network) — default mode
  python -m scripts.run_ingest --sport baseball_mlb --source fixture

  # Ingest a second fixture snapshot to demonstrate line movement
  python -m scripts.run_ingest --sport baseball_mlb --source fixture \
        --fixture-suffix _t2

  # Ingest live (requires THE_ODDS_API_KEY in env) — DO NOT run until the
  # owner has provisioned the key.
  python -m scripts.run_ingest --sport baseball_mlb --source live

This is a single-shot runner. A scheduled loop (cron / asyncio interval) wraps
this once we go live; kept single-shot here to stay memory-light and testable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python scripts/run_ingest.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edgewire.db.database import connect, init_db  # noqa: E402
from edgewire.ingest.pipeline import ingest_fetch_result  # noqa: E402
from edgewire.providers.fixture import FixtureTheOddsAPIProvider  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="EdgeWire odds ingestion runner")
    ap.add_argument("--init", action="store_true", help="create schema and exit")
    ap.add_argument("--sport", default="baseball_mlb")
    ap.add_argument("--source", choices=["fixture", "live"], default="fixture")
    ap.add_argument("--fixture-suffix", default="", help="e.g. _t2 for 2nd snapshot")
    ap.add_argument(
        "--markets", default="h2h,spreads,totals",
        help="comma-separated market keys",
    )
    args = ap.parse_args()

    conn = connect()
    init_db(conn)
    if args.init:
        print(f"Schema initialized at {conn.execute('PRAGMA database_list').fetchall()[0][2]}")
        return 0

    markets = tuple(m.strip() for m in args.markets.split(",") if m.strip())

    if args.source == "fixture":
        provider = FixtureTheOddsAPIProvider()
        # Support alternate snapshot fixtures via suffix by temporarily pointing
        # the provider at a renamed sport key path.
        sport_for_fixture = args.sport + args.fixture_suffix
        try:
            result = provider.fetch_odds(sport_for_fixture, markets=markets)
        except FileNotFoundError:
            # fall back: suffix appended to filename, not sport key
            import json as _json
            fpath = (
                Path(__file__).resolve().parents[1]
                / "data" / "fixtures"
                / f"the_odds_api_{args.sport}{args.fixture_suffix}.json"
            )
            from edgewire.providers.the_odds_api import _parse_events
            from edgewire.providers.base import FetchResult
            payload = _json.loads(fpath.read_text())
            result = FetchResult(events=_parse_events(payload))
    else:
        from edgewire.providers.the_odds_api import TheOddsAPIProvider
        provider = TheOddsAPIProvider()
        result = provider.fetch_odds(args.sport, markets=markets)

    summary = ingest_fetch_result(
        conn, result, provider_name=provider.name, sport_key_hint=args.sport
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
