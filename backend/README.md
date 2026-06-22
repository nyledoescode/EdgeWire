# EdgeWire — Odds Ingestion Backend

Foundational data backend for EdgeWire's sportsbook **intelligence** platform.
This layer pulls odds from a provider, normalizes them, and lands them in a
time-series store designed for **line-movement history** and **Closing Line
Value (CLV)**. It is deliberately provider-agnostic so we can start lean on
**The Odds API** and later swap in a premium feed (OddsJam / SportsDataIO)
without rewriting schema or math.

> **Scope note:** This module stores *raw normalized market data only*. The
> no-vig fair-value / EV / CLV math is implemented separately, strictly against
> the Quant's approved spec (see `methodology/` — pending). Nothing here invents
> probabilities or edges.

## Layout

```
edgewire/
  odds_math.py            Mechanical odds conversions (American<->decimal). No EV.
  db/
    schema.sql            Time-series odds schema (SQLite now, Postgres-portable)
    database.py           Connection + init/reset helpers (stdlib sqlite3)
  providers/
    base.py               OddsProvider Protocol + normalized record dataclasses
    the_odds_api.py       The Odds API v4 adapter (+ pure _parse_events)
    fixture.py            Replays saved JSON payloads — no key, no network
  ingest/
    pipeline.py           Normalize -> upsert dims -> append dedup'd snapshots
data/
  fixtures/               Sample The Odds API v4 payloads (MLB) for dev/tests
scripts/
  run_ingest.py           CLI runner (--init / fixture / live)
tests/                    pytest sanity tests (13, all passing)
docs/                     Schema & architecture notes
methodology/              Quant specs land here (Spec 01 EV, Spec 02 CLV)
```

## Quickstart (no API key required)

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python scripts/run_ingest.py --init
.venv/bin/python scripts/run_ingest.py --sport baseball_mlb --source fixture
# demonstrate line movement with a 2nd snapshot:
.venv/bin/python scripts/run_ingest.py --sport baseball_mlb --source fixture --fixture-suffix _t2
.venv/bin/python -m pytest -q
```

## Design highlights

- **Append-only `odds_snapshot`** — one row per (event, book, market, selection,
  observed_at). Prices are never updated in place; a new row is written only
  when price/line changes. This preserves full movement history + an auditable
  trail for CLV.
- **CLV-ready** — first observation per selection is flagged `is_opening`;
  closing line is derived as the last snapshot at/before `commence_time`
  (not stored as a mutable column, so it can't be silently rewritten).
- **Provider abstraction** — everything downstream consumes `Normalized*`
  dataclasses, never provider-native JSON. Swapping feeds = new adapter only.
- **Memory-light** — stdlib `sqlite3`, no ORM, single-shot runner. A scheduled
  loop wraps the runner once live.

## What I need from the owner (BLOCKERS)

1. **`THE_ODDS_API_KEY`** — required only for *live* ingestion. All dev/tests run
   on fixtures today; do not provision until we're ready to validate against the
   live feed. (Free tier is fine to start.)
2. **A git repository** — none is linked yet. This is currently built in
   `/home/team/shared/edgewire` with no version control. Please create/connect a
   repo so we can commit history and collaborate safely.

## Pending dependency

- **Quant Spec 01** (no-vig fair value + EV) and **Spec 02** (CLV) — the EV/CLV
  compute modules are intentionally NOT written until these land in
  `methodology/`. Schema already captures everything those specs will need.
