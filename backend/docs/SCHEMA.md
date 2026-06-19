# EdgeWire Data Schema & Architecture

This document explains the time-series odds schema and how it supports the two
hardest requirements: **line-movement history** and **Closing Line Value (CLV)**.

## Entity model

```
sport (1) ──< event (1) ──< odds_snapshot >── (1) bookmaker
                                  │
                                  └── (1) market_type

ingest_run (1) ──< odds_snapshot      (provenance)
```

- **sport** — leagues we track. `sport_key` mirrors The Odds API
  (`baseball_mlb`, `americanfootball_nfl`, `basketball_nba`).
- **bookmaker** — sportsbooks. `is_sharp=1` marks fair-value anchor books
  (Pinnacle, Circa, BetOnline) the quant's EV layer will lean on.
- **market_type** — `h2h` (moneyline), `spreads`, `totals`, plus props later.
  `has_line=1` means the market carries a `point`.
- **event** — a game. Keyed by `(provider, provider_event_id)`. `commence_time`
  is the CLV cutoff anchor. Scores/`completed` fill in for settlement later.
- **odds_snapshot** — the fact table (see below).
- **ingest_run** — one row per ingestion pass, with quota accounting for paid
  APIs and ok/error status for auditability.

## The fact table: `odds_snapshot`

Grain: **one row per `(event, bookmaker, market_type, selection, observed_at)`**.

Key columns:
- `selection` — team / "Over" / "Under" / player+side.
- `point` — the line (spread or total); `NULL` for moneyline.
- `price_american` — canonical price storage (e.g. `-110`, `+145`).
- `price_decimal` — derived, cached for fast downstream math.
- `book_last_update` — provider's `last_update` for that market.
- `observed_at` — when *we* captured it (our snapshot time).
- `is_opening` — `1` only on the first observation of a selection key.
- `ingest_run_id` — provenance.

### Why append-only?

We never UPDATE a price. Each ingestion run INSERTs a new row **only when the
price or line differs** from the most recent observation for that key. Benefits:

1. **Full movement history** — every genuine move is a row; reconstructing a
   line chart is `ORDER BY observed_at`.
2. **Auditable CLV** — opening and closing are real observed rows, not numbers
   we can quietly overwrite. This is core to EdgeWire's "transparent,
   verifiable" positioning.
3. **Compact** — dedup means stable lines don't bloat the table.

### How CLV is derived (not stored)

- **Opening line** = the `is_opening=1` row (or earliest `observed_at`).
- **Closing line** = the last snapshot with `observed_at <= event.commence_time`.

CLV is computed at query/compute time from these two observed rows, per the
quant's Spec 02. We deliberately avoid a mutable `closing_line` column so the
track record can't be retroactively edited.

## Indexes

- `idx_snapshot_line (event, market, book, selection, observed_at)` — movement &
  CLV reconstruction.
- `idx_snapshot_opening` — partial index on `is_opening=1` for fast opening
  lookups.
- `idx_event_commence` — windowing events near tip-off for closing capture.

## View: `v_latest_odds`

Returns the most recent observation per `(event, book, market, selection)` —
the basis for **line shopping** (best available price) and the EV screen.

## Provider abstraction

`providers/base.py` defines the `OddsProvider` Protocol and the `Normalized*`
dataclasses that are the contract with ingestion. `the_odds_api.py` implements
the v4 adapter; `fixture.py` replays saved payloads through the *same*
`_parse_events` path. Adding OddsJam/SportsDataIO later = one new adapter that
emits the same normalized records — no schema or ingestion changes.

## Portability to Postgres

Schema uses portable types (`INTEGER`, `TEXT`, `REAL`) and ISO8601 string
timestamps. Moving to Postgres means: swap `db/database.py` for a psycopg
connection, change `INTEGER PRIMARY KEY` -> `BIGSERIAL`/`IDENTITY`, and convert
the partial index syntax. Ingestion and provider code are untouched.
