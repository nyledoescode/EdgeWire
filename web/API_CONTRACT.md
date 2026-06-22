# EdgeWire Frontend ⇄ Backend Data Contract (v0.2)

This is the shape the web app consumes. The frontend is built so that swapping
mock → live is a one-line change per endpoint (see `src/api/client.ts`).
Canonical TypeScript types live in `src/types.ts` — treat that file as the
source of truth.

**Reconciled against** the backend's `docs/API_CONTRACT_RECONCILIATION.md`,
quant Spec 01 (fair value/EV), Spec 02 (CLV), and Spec 03 (line movement). All
deltas the backend raised are folded in below.

## Conventions
- **Odds**: American odds throughout (e.g. `-110`, `+145`), as numbers.
- **Probabilities**: floats `0..1`.
- **EV**: fraction, e.g. `0.042` = +4.2% EV. (Backend stores `ev_pct` per Spec 01
  and divides by 100 at the response boundary — wire value is the fraction.)
- **CLV**: percentage points, e.g. `2.3` = beat the close by 2.3pp.
- **Movement deltas**: percentage points of **no-vig consensus probability**
  (Spec 03 §0), NOT raw price.
- **Timestamps**: ISO-8601 UTC strings.

## Authoritative computation boundaries (binding)
- `fairProb`/`fairPrice` are **server-side** (Spec 01 engine). The frontend
  renders them and must NOT re-derive no-vig in the browser.
- `isPlusEv` is the **server-side** +EV gate (Spec 01 §4.3: positive EV AND
  confidence ≠ low). The UI highlights on this flag, not its own `ev > 0`.
- CLV rates are **never** shown without sample size `n` and a confidence
  interval (Spec 02 §3.2), and a sub-30 sample is never headlined (§3.3).
- We **never** fabricate public ticket/handle % — without a splits feed we show
  the labeled Sharp-Move proxy (Spec 03 §3.5).

## Endpoints

### `GET /api/ev-screen?sport=NFL&market=h2h`
Returns `EvScreenResponse`:
```jsonc
{
  "generatedAt": "2026-06-15T12:00:00Z",
  "capabilities": {              // Spec 03 §5.3 — UI degrades off these
    "splitsAvailable": false,
    "sharpCoverage": "partial",  // "full" | "partial" | "none"
    "rlmMode": "sharp_proxy",    // "true_rlm" once splits feed exists
    "steamFidelity": "coarse"    // "fine" | "coarse" (polling cadence)
  },
  "events": [
    {
      "id": "evt_123",
      "sport": "NFL", "league": "NFL",
      "startTime": "2026-06-15T20:00:00Z",
      "homeTeam": "Kansas City Chiefs",
      "awayTeam": "Buffalo Bills",
      "trackedFrom": "2026-06-14T16:00:00Z",   // earliest snapshot we captured (Spec 03 §1.1)
      "signals": [                              // fired movement signals (Spec 03 §2-4)
        {
          "type": "steam",                      // "steam" | "sharp_move" | "rlm"
          "selection": "Buffalo Bills",
          "direction": "toward",                // "toward" | "away" (rel. to selection)
          "magnitudePp": 5.1,                   // no-vig prob delta in pts
          "windowSeconds": 480,
          "nBooksMoved": 6, "booksTotal": 8,
          "sharpLed": true,
          "ticketPct": null, "handlePct": null, // RLM-only, null without splits feed
          "splitsSource": null,
          "detectedAt": "2026-06-15T11:20:00Z"
        }
      ],
      "markets": [
        {
          "type": "h2h", "label": "Moneyline",
          "outcomes": [
            {
              "name": "Buffalo Bills",
              "fairProb": 0.45,                 // server-side (Spec 01)
              "fairPrice": 122,
              "bestPrice": 102, "bestBook": "fanduel",
              "ev": 0.031,                      // fraction
              "confidence": "high",             // "high" | "medium" | "low" (Spec 01 §5)
              "isPlusEv": true,                 // server-side gate (Spec 01 §4.3)
              "stale": false,                   // best price from a stale observation?
              "prices": [
                { "book": "fanduel", "bookName": "FanDuel", "price": 102, "point": null, "updatedAt": "...", "isBest": true }
              ],
              "movement": [                      // no-vig prob series (Spec 03 §0)
                { "t": "2026-06-14T16:00:00Z", "consensusFairProb": 0.42, "price": 138, "point": null },
                { "t": "2026-06-15T11:20:00Z", "consensusFairProb": 0.45, "price": 122, "point": null }
              ],
              "fairProbDeltaPp": 3.0,            // open→now consensus prob delta (pp) — drives ▲/▼
              "americanDelta": 16,               // raw cents move (secondary display)
              "lineMovePoints": null             // spread/total number move, signed
            }
          ]
        }
      ]
    }
  ]
}
```

**Movement direction (Spec 03 §1.2/§6):** the Movement page's `▲/▼` reads from
`fairProbDeltaPp` (no-vig consensus prob), NOT raw price. A lengthening price can
coincide with the fair moving against the side; American "cents" is secondary.
The sparkline plots `consensusFairProb` when present, else falls back to `price`.

### `GET /api/clv-summary?window=90d`
Returns `ClvSummary`:
```jsonc
{
  "sampleSize": 9,
  "beatRate": 0.778,
  "beatRateCI95": [0.45, 0.94],        // Wilson 95% CI — REQUIRED with the rate (Spec 02 §3.2)
  "avgClvPct": 1.95,
  "avgClvPctCI95": [0.30, 3.60],       // t-based 95% CI
  "displayGate": "small_sample",        // "building"|"small_sample"|"full"|"verified" (§3.3)
  "window": "last 90 days",
  "generatedAt": "2026-06-15T12:00:00Z",
  "records": [
    { "id": "clv_1", "placedAt": "...", "sport": "NFL", "event": "KC @ BUF",
      "market": "Spread", "selection": "KC -1.5",
      "takenPrice": -108, "closingPrice": -120, "clvPct": 2.62, "result": "win" }
  ]
}
```
**Binding honesty rules (Spec 02 §3):** the UI renders the CI next to every rate,
shows `n`, and suppresses/soft-labels the headline when `displayGate` is
`building` or `small_sample` (never headline a sub-30 sample). Full graded
sample is published — wins, losses, pushes — no cherry-picking.

## Tier gating (frontend UX + backend enforcement)
- **free**: delayed snapshot, ML only, top books only.
- **pro**: real-time, all markets, line movement, alerts.
- **elite**: arbitrage/middling, API access, advanced models.

The frontend gates views client-side for UX; the backend MUST enforce tier on
returned data (don't ship Elite arbitrage data to a Free token). Proposed auth:
bearer token, tier in a `tier` JWT claim — backend reads tier from that claim.

## Resolved questions
1. **Auth/tier source** — bearer token + `tier` JWT claim (backend confirmed it
   will read from whatever claim the auth layer exposes). ✅ agreed.
2. **fairProb/fairPrice** — server-side (Spec 01). ✅ frontend renders only.
3. **ev units** — fraction on the wire; backend converts `ev_pct`/100. ✅ no change.

## Remaining deltas flagged to backend
- **Movement series source:** frontend now expects `movement[].consensusFairProb`
  plus per-outcome `fairProbDeltaPp`/`americanDelta`/`lineMovePoints`. Backend's
  current `movement()` helper returns raw price history only; the `movement_point`
  table (Spec 03 §5.2) with `consensus_fair_prob` is the source once the movement
  engine lands. Until then the UI falls back to plotting price.
- **Signals feed:** `EventRow.signals[]` maps to the `movement_signal` table
  (Spec 03 §5.2). Field names align (camelCase here ↔ snake_case in SQL).
- **Capabilities object:** `capabilities` on the ev-screen response maps to the
  §5.3 flags. Please emit it even pre-signals so the UI degrades correctly.
- **CLV CI/gate:** `beatRateCI95`, `avgClvPctCI95`, `displayGate` — backend
  confirmed it will emit these; types are ready frontend-side.
