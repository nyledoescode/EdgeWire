# EdgeWire

AI sportsbook **intelligence** platform — real-time odds intelligence and betting
analytics (line shopping, +EV detection, line movement, CLV tracking) built on
transparent, auditable data. Tools & data lane (à la OddsJam / Outlier), not a
"guaranteed picks" tout.

## Monorepo layout

```
backend/          Python intelligence backend (odds ingestion, EV/CLV engine, API)
web/              Vite + React + TS web app (subscriber UI)        [added separately]
docs/methodology/ Quant methodology specs (no-vig/EV, CLV, line movement) + vectors
```

## Backend
Python (stdlib + sqlite3, memory-light). Ingests odds from The Odds API (provider-
abstracted), stores a time-series odds DB, computes no-vig fair value, multi-book
consensus, +EV, and Closing Line Value per the quant's methodology specs. See
[`backend/README.md`](backend/README.md).

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/run_ingest.py --init
.venv/bin/python scripts/run_ingest.py --sport baseball_mlb --source fixture
.venv/bin/python -m pytest -q
```

## Methodology
The intelligence math is specified in [`docs/methodology/`](docs/methodology/) and
implemented test-first against the quant's canonical `test-vectors.json`. All
outputs are probabilities/EV — never guarantees (compliance-first).
