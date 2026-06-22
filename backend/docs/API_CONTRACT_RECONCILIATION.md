# Backend ⇄ Frontend API Contract Reconciliation

**Author:** Data/Backend Engineer
**Reconciles:** `/home/team/shared/edgewire-web/API_CONTRACT.md` + `src/types.ts`
(frontend) against `/home/team/shared/methodology/01-no-vig-fair-value-and-ev.md`
(Spec 01, source of truth for intelligence fields) and Spec 02 (CLV).

**Verdict:** the two contracts are **compatible**. The frontend's `EvScreenResponse`
is a UI-shaped projection of Spec 01's per-outcome emission. Below is the exact
field mapping the EV-screen endpoint will implement, plus a small list of deltas
the fullstack engineer should confirm. No structural redesign needed on either side.

---

## 1. `GET /api/ev-screen` — field mapping

Backend assembles events from `event` + `v_latest_odds` (line shopping) and the
EV/fair-value engine's per-outcome output (Spec 01 §5). Mapping to the frontend's
`Outcome` type:

| Frontend field (`types.ts`) | Source | Notes |
|---|---|---|
| `EventRow.id` | `event.provider_event_id` | stable string id |
| `EventRow.sport` / `league` | `sport.title` | frontend `Sport` enum; backend sends `sport_key` too |
| `startTime` | `event.commence_time` | ISO-8601 UTC |
| `homeTeam`/`awayTeam` | `event.home_team`/`away_team` | |
| `Market.type` | `market_type.market_key` | `h2h`/`spreads`/`totals` |
| `Outcome.name` | `odds_snapshot.selection` | |
| `Outcome.fairProb` | Spec 01 `consensus_fair_prob` (leave-one-out, outlier-free, renormalized) | **server-side** (answers their open Q2) |
| `Outcome.fairPrice` | Spec 01 `consensus_fair_american` | from `fairProb` via §1.3 |
| `Outcome.bestPrice`/`bestBook` | best `price_american` across books from `v_latest_odds` | line shopping |
| `Outcome.ev` | Spec 01 `ev_pct / 100` | **DELTA — see §2.1** |
| `Outcome.prices[]` | `v_latest_odds` rows per book | `{book, bookName, price, point, updatedAt(=book_last_update), isBest}` |
| `Outcome.movement[]` | `odds_snapshot` history for the outcome | `{t(=observed_at), price, point}` |

The read helpers in `edgewire/api.py` (`list_events`, `line_shop`, `movement`)
already return the raw-market half of this; the EV engine adds `fairProb`,
`fairPrice`, `ev` once built (next task).

## 2. Deltas the fullstack engineer should confirm

### 2.1 `ev` units — RESOLVED, frontend is fine
Frontend `ev` is a **fraction** (`0.042` = +4.2%). Spec 01 emits `ev_pct` (`7.8`
= +7.8%). Backend will divide by 100 at the endpoint boundary so the wire value
matches the frontend. **No change needed frontend-side.** (Internally we keep
`ev_pct` per Spec 01 §5; conversion happens only in the response mapper.)

### 2.2 Server-side fair value (their open Q2) — ANSWERED
`fairProb`/`fairPrice` are computed **server-side** by the Spec 01 engine, not
derived in the browser. The frontend should treat them as authoritative and not
re-derive no-vig. This is binding: the quant spec owns the math, and CLV grading
(Spec 02) must reference the same server-computed consensus for consistency.

### 2.3 Confidence + flags — ADDITIVE fields the UI will want
Spec 01 §5 emits `consensus_n_books`, `consensus_confidence` (high/medium/low),
`is_plus_ev`, `ev_threshold_used`, `flags[]`, `stale`. These aren't in the
current `Outcome` type. **Recommend** the frontend add optional fields:
`confidence?: 'high'|'medium'|'low'`, `isPlusEv?: boolean`, `stale?: boolean`.
The +EV screen should only *highlight* rows where `is_plus_ev === true` AND
`confidence !== 'low'` (Spec 01 §4.3 gates). Backend will send these; UI can
ignore until ready.

### 2.4 `movement[]` should switch to no-vig prob direction (Spec 03 §6)
Currently the sparkline diffs raw American price. Spec 03 §1.3 shows raw price
can mislead (a lengthening price while the no-vig fair moves the other way).
When the movement engine lands, backend will expose a consensus-fair-prob series
(`movement_point`); recommend the UI source the ▲/▼ direction from that and keep
American as the secondary display. Non-blocking for v1.

## 3. `GET /api/clv-summary` — mapping + honesty guards

Frontend `ClvSummary`/`ClvRecord` maps onto Spec 02's `bet_signal` ledger +
aggregate store:

| Frontend | Source (Spec 02) |
|---|---|
| `ClvSummary.sampleSize` | count of `clv_status='graded'` bets |
| `ClvSummary.beatRate` | `BTC_rate` (§3.1) |
| `ClvSummary.avgClvPct` | `avg_CLV_pct` (§3.1) |
| `ClvRecord.takenPrice` | `bet_signal.bet_american` |
| `ClvRecord.closingPrice` | `bet_signal.closing_fair_american` |
| `ClvRecord.clvPct` | `bet_signal.clv_pct` |
| `ClvRecord.result` | win/loss/push/pending (settlement) |

**DELTA — Spec 02 §3.2 compliance (binding):** a beat-rate/avg-CLV must NEVER be
shown without **sample size `n` and a confidence interval**. The current
`ClvSummary` has `sampleSize` but **no CI fields**. Backend will additionally
emit `beatRateCI95: [lo, hi]` (Wilson) and `avgClvPctCI95: [lo, hi]` (t-based),
plus a `displayGate` ('building'|'small_sample'|'full'|'verified') per §3.3.
**Frontend must render the CI and never headline a sub-30 sample.** Please add
these optional fields to `ClvSummary`. This is not optional polish — it's the
core honesty/compliance posture of the product.

## 4. Tier gating, auth (their open Q1)
Backend will enforce tier on returned data (Free = delayed/ML/top-books only),
not just trust the client. Auth mechanism (JWT claim vs `/api/me`) is owned by
the fullstack engineer's auth layer; backend will read tier from whatever claim
they expose. Proposing: bearer token, tier in a `tier` JWT claim, backend
filters the slate accordingly. Confirm and I'll wire to it.

## 5. Summary of asks for the fullstack engineer
1. Add optional `confidence`, `isPlusEv`, `stale` to `Outcome` (§2.3).
2. Add `beatRateCI95`, `avgClvPctCI95`, `displayGate` to `ClvSummary` (§3) —
   **required for compliant CLV display.**
3. Agree fair value is server-side (§2.2) — don't re-derive in the browser.
4. (Later) source movement ▲/▼ from no-vig prob series (§2.4).

Everything else aligns as-is. I own keeping these in sync as the EV/CLV engine lands.
