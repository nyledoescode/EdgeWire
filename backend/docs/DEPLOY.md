# EdgeWire API — Render Deploy

The intelligence API is **pure Python stdlib** (no runtime pip dependencies). It
serves fixture-backed MLB data today and swaps to live odds once
`THE_ODDS_API_KEY` is provisioned — no math or code rewrite.

## Fastest path: Blueprint (recommended)
The repo ships `render.yaml` at the root. In Render: **New → Blueprint → point at
this repo**. It provisions the `edgewire-api` web service with the correct root
dir, build/start commands, health check, and env vars. Nothing to type by hand.

> **Free tier: no persistent disk.** Render rejects a free-tier Blueprint that
> declares a disk ("disks are not supported for free tier services"), so
> `render.yaml` ships with the disk block **commented out** and `EDGEWIRE_DB`
> pointed at ephemeral `/tmp/edgewire.db`. This resets on every restart /
> redeploy, which is fine today: the app self-seeds the checked-in MLB fixtures
> into an empty DB on boot, so endpoints return real data immediately. See
> **Persistent disk** below for the paid-upgrade path to keep history.

## Manual setup (fallback — if you configure the service by hand)
Create a **Web Service** from the repo with:

| Field            | Value                          |
|------------------|--------------------------------|
| Root Directory   | `backend`                      |
| Runtime          | Python                         |
| Build Command    | `python --version`             |
| Start Command    | `python scripts/serve_api.py`  |
| Health Check Path| `/api/health`                  |

> **Build Command MUST NOT be `pip install -r requirements.txt`** — that file
> does not exist (only `requirements-dev.txt` for pytest, not needed at runtime).
> Render's default build tries `requirements.txt` and fails; override it with the
> no-op `python --version`.

### Persistent disk (paid plans only — optional today)
**Free tier cannot mount a disk**, so leave the DB on ephemeral `/tmp` (it
self-seeds fixtures on boot — no data loss that matters while we run on
fixtures). To **persist** the append-only odds/CLV time-series across restarts
you must upgrade to a paid **Starter** plan, then:
- Uncomment the `disk:` block in `render.yaml` (or add a disk in the dashboard):
  - **Mount path:** `/var/data`
  - **Size:** 1 GB
- Point `EDGEWIRE_DB` back at `/var/data/edgewire.db`.

Nothing in the app changes — this is purely a storage/durability upgrade.

### Environment variables
| Var                 | Value / note                                              |
|---------------------|-----------------------------------------------------------|
| `PORT`              | Injected by Render automatically — **do not set**. The app binds `$PORT` on `0.0.0.0`. |
| `EDGEWIRE_DB`       | Free tier: `/tmp/edgewire.db` (ephemeral, self-seeds on boot). Paid+disk: `/var/data/edgewire.db`. |
| `THE_ODDS_API_KEY`  | **Later, owner-provisioned.** Absent = fixture mode, zero API spend. |

## What happens on boot
`serve()` reads `PORT` first (then `EDGEWIRE_API_PORT`, then `8000`), binds
`0.0.0.0`, and **self-seeds an empty DB** with the checked-in MLB fixtures via
`edgewire/ingest/bootstrap.py`. A fresh instance therefore returns real data
immediately (e.g. Boston Red Sox **+6.76% EV** on `/api/ev-screen?sport=MLB`).
Seeding is idempotent — a restart against a populated disk is a no-op and never
clobbers accumulated history.

## Endpoints
- `GET /api/health` → `200 {"status":"ok"}` (Render health check)
- `GET /api/ev-screen?sport=MLB` → +EV screen (de-vigged fair value, best price)
- `GET /api/clv-summary?window=90d` → CLV with honesty fields / `displayGate`
- `GET /api/capabilities` → honest degraded-signal flags

## Going live later (THE_ODDS_API_KEY)
1. Owner provisions `THE_ODDS_API_KEY` as a Render env var (Dashboard, `sync:false`).
2. Enable ingest polling. A Render disk mounts to only **one** service, so the
   poller should run as a background thread inside this web service (gated on the
   key) or the store migrates to Postgres (a `db/database.py` swap) with a
   standalone `cron` service. Until then there is **no live polling and no spend**.

## Local parity with Render
```bash
cd backend
rm -f /tmp/ew.db
PORT=10000 EDGEWIRE_DB=/tmp/ew.db python scripts/serve_api.py
curl localhost:10000/api/health          # 200
curl "localhost:10000/api/ev-screen?sport=MLB"   # Red Sox +6.76% EV from empty DB
```
