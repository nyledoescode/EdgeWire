# Methodology Spec 03 — Line Movement, Steam & Reverse Line Movement Signals

**Owner:** Quant Analyst
**Status:** v1.0 — ready for engineering
**Depends on:** Spec 01 (de-vig §2, multi-book consensus §3, odds conversion §1, book weights/`is_sharp`) and Spec 02 (time-series capture, opening/closing capture). Read both first.
**Aligned to existing build:** uses the backend's `odds_snapshot` append-only schema (`is_opening`, `observed_at`, `book_last_update`, `commence_time`, `bookmaker.is_sharp`) and powers the frontend **Line Movement** page (`src/pages/Movement.tsx`) + the report mockup's "Steam / RLM / open→close" block.
**Audience:** Data/Backend Engineer (compute + schema), Fullstack (Movement page semantics), Growth (claim framing).

> **Compliance note (binding).** Every signal in this spec is a **probabilistic market observation**, never a guarantee or a "bet this" instruction. Steam/RLM/sharp-divergence describe *what the market is doing*; they are context, not promises. This matches the Movement page copy already in the build ("context, not a signal to chase"). No signal output may use "guaranteed," "lock," or a manufactured hit-rate. The one place the word "guaranteed" is legitimate is **arbitrage margin** (a real locked margin) — that is a separate Elite feature, not a movement signal, and is out of scope here.

---

## 0. Foundations: everything is measured in no-vig probability space

A raw price move conflates two things: a genuine change in the market's belief, and a change in the book's vig/positioning. To measure movement **honestly and comparably across markets**, we convert every observation to a **no-vig consensus fair probability** (Spec 01 §2–§3) and measure movement as a **probability delta**. Price/American deltas are also computed for display (the Movement page shows `▲/▼` in American points), but **all thresholds and signals are defined on no-vig probability**, because:
- A move from −110 to −120 (≈ −0.022 prob in fair space) is small; a move from +150 to +120 (≈ +0.051 prob) is large — raw "cents" hide that.
- Probability space is comparable across moneyline, spread-price, totals-price, and props.

**Per-outcome movement series.** For an `(event, market, selection[, point])`, reconstruct from `odds_snapshot` (ordered by `observed_at`):
- per-book de-vigged prob over time (Spec 01 §2, within each book's market),
- the **consensus** no-vig fair prob over time (Spec 01 §3: staleness filter, robust-z outlier filter, weighted average, renormalize).

Define three reference points on the consensus series:
```
p_open    = consensus fair prob at the OPENING snapshot   (first is_opening-anchored consensus)
p_now     = consensus fair prob at the latest snapshot
p_close   = consensus fair prob at the closing capture     (Spec 02 §1.2)  [only post-close]
```

---

## 1. Line Movement Tracking

### 1.1 Opening line capture

The schema already flags the first observation per `(event, book, market, selection)` with `is_opening = 1`. The **consensus opening** is the consensus fair prob computed from the earliest snapshot in which **≥ 3 books** have posted (Spec 01 confidence ≥ medium). Rationale: a single book's opener is noisy and often a "feeler" line; wait for a real multi-book market to call it "the open." Store, per outcome:
```
opening_consensus_prob   p_open
opening_consensus_american  (Spec 01 §1.3 of p_open)
opening_observed_at
opening_n_books
```
> **The Odds API caveat (flag):** true openers are easy to miss if our first poll is hours after the book opened the market. We can only call "open" the earliest snapshot **we captured**. Store `opening_observed_at` so the UI can honestly label "tracked from {time}" rather than implying we caught the literal first number. Premium feeds publish explicit opening lines; budget tier = "earliest we observed."

### 1.2 Movement deltas

```
move_prob_open_now   = p_now   − p_open          # primary, no-vig
move_prob_open_close = p_close  − p_open          # post-close only
move_american_open_now = american(p_now) − american(p_open)   # display ("cents")
```
Sign convention: **positive prob delta = market moved TOWARD this outcome** (it became more likely / its fair price shortened). The Movement page's `▲` should map to a positive prob delta for that outcome (currently it diffs raw price; recommend switching the delta source to no-vig consensus prob — see §6 frontend note).

### 1.3 Worked example — totals price move

Game total, **Over** selection. Opening market: Over −110 / Under −110. Current market: Over +104 / Under −124.
```
Open  (de-vig):  Over fair p = 0.5000
Now   (de-vig):  q_over = 100/204 = 0.49020, q_under = 124/224 = 0.55357
                 M = 1.04377 → p_over_now = 0.49020/1.04377 = 0.46964
move_prob_open_now = 0.46964 − 0.5000 = −0.0304   (Over became LESS likely; money to the Under)
```
Display: "Over O8.5: −110 → +104 (▼ 3.0 pts fair prob)". (Note the *price* on Over got longer, +104, but the no-vig fair moved against Over — the Movement page should show the fair-prob direction, not be fooled by the lengthening price.)

### 1.4 Spread/total NUMBER moves vs price moves
Two distinct movements exist for spreads/totals:
- **Price move** at a fixed number (e.g. −3 from −110 to −120) → captured in prob space as above.
- **Number move** (e.g. +6.5 → +5, or total 8.5 → 8) → the *line itself* moved. Track `point` changes from `odds_snapshot.point`. A number move is more significant than a price move (it crosses potential key numbers). Store both:
```
line_move_points = point_now − point_open      # signed, in points
```
Key-number weighting (NFL 3,7,10; NBA/totals less peaked) is deferred to a later historical/key-number spec; for v1, **report** number moves and flag when a move crosses a key number, but don't yet model the win-prob value of the half-point.

---

## 2. Steam Move Detection

A **steam move** is a *fast, large, broad-based* move in the same direction across many books in a short window — the market signature of sharp money / syndicate action hitting multiple books near-simultaneously. The art is requiring **all three** of magnitude, velocity, and breadth so we don't fire on a single book's correction or a stale-quote artifact.

### 2.1 Definition (all conditions must hold)

For an outcome over a sliding time window `Δt`:

```
Let books B = set of non-stale books (Spec 01 §3.3) quoting the outcome at both ends of the window.
For each book b in B, let δ_b = p_b(t) − p_b(t−Δt)   (that book's own no-vig prob change).

STEAM(outcome) is flagged when ALL of:
  1. MAGNITUDE:  |median_b(δ_b)| ≥ M_steam            (consensus-level move size)
  2. VELOCITY:   the move happened within window Δt ≤ T_steam
  3. BREADTH:    fraction of books moving in the SAME direction ≥ F_steam
                 AND count of same-direction books ≥ N_steam
  4. DIRECTIONAL COHERENCE: sign(δ_b) agrees for ≥ N_steam books (not net-zero churn)
```

### 2.2 Default thresholds (config-driven, tunable)

| Param | Default | Meaning |
|---|---|---|
| `M_steam` | **≥ 0.030** (3.0 pts no-vig prob) | median per-book move over the window |
| `T_steam` | **≤ 10 min** | window length (mockup shows "8 min") |
| `F_steam` | **≥ 0.60** | ≥60% of quoting books moved same direction |
| `N_steam` | **≥ 4 books** | absolute floor on breadth |
| min books present | **≥ 5** | don't evaluate steam on thin coverage |

Tier overrides: props use `M_steam ≥ 0.045`, `N_steam ≥ 3` (thinner coverage). Live/in-play uses `T_steam ≤ 3 min`.

### 2.3 False-positive guards (REQUIRED)
1. **Single-book exclusion:** a move at one book (even huge) is **never** steam. Breadth (`N_steam ≥ 4`) enforces this.
2. **Staleness:** exclude any book whose `book_last_update` didn't actually change in the window — a book that simply got re-polled with the same number is not "moving." Compare on `book_last_update`, not `observed_at`.
3. **Outlier book:** if the move is driven only by books that Spec 01 §3.4 flagged as outliers, suppress (it's a soft-book correction, not market steam).
4. **Vig-repricing artifact:** ensure the move shows in **no-vig** space, not just because a book widened/narrowed its hold symmetrically.
5. **Debounce:** once flagged, don't re-flag the same outcome for `cooldown` (default 15 min) unless a fresh move of `≥ M_steam` occurs.

### 2.4 Worked example — moneyline steam

Underdog team moves from **+150 to +120** across 6 of 8 books in 8 minutes.
```
Per-book de-vig (vs the other side), consensus:
  start:  +150 / −180  → fav side de-vig... dog fair p_start = 0.3836
  end:    +120 / −145  → dog fair p_end   = 0.4344
median δ ≈ p_end − p_start = +0.0508   (5.1 pts no-vig prob)
MAGNITUDE: 0.0508 ≥ 0.030 ✓
VELOCITY:  8 min ≤ 10 min ✓
BREADTH:   6/8 = 0.75 ≥ 0.60 ✓  and 6 ≥ 4 ✓
DIRECTION: all 6 moved toward the dog ✓
→ STEAM flagged on the underdog ML (sharp money likely on the dog).
```
Display (matches mockup style): "🔥 Steam: [Dog] ML +150 → +120 across 6 books in 8 min (+5.1 pts fair prob)." Always paired with the compliance line that this reflects market action, not a recommendation.

### 2.5 Velocity score (for ranking, optional)
```
steam_velocity = |median δ| / Δt_minutes     (no-vig prob per minute)
```
Use to sort the steam feed (fastest/biggest first). Display only as a relative intensity, never as an edge guarantee.

---

## 3. Reverse Line Movement (RLM)

**RLM** = the line moves **against** the side the betting *public* is on (e.g. 71% of tickets on Team A, but the line moves toward Team B). It implies the money (handle), not the ticket count, is on the other side — a classic sharp/public divergence.

### 3.1 Hard data dependency — FLAG

> **RLM CANNOT be computed from The Odds API.** It requires **betting-split data**: the % of **tickets** (bet count) and ideally % of **handle** (money) on each side, per market. The Odds API provides **prices only — no splits, no ticket/handle data.** This is a hard gap, not a tuning problem.

**What's required to ship real RLM:**
- A **betting-splits feed**. Known sources (require their own contracts/keys, owner approval, and cost): **Sports Insights / Action Network ("Action Labs") split data, Pregame, Don Best (legacy), VSiN "Money vs Tickets," BetQL, or sportsbook-published "consensus"/bet-percentage endpoints (DraftKings/ESalize-style) where available.** Some books publish bet% on select markets; coverage is partial and TOS-restricted.
- Minimum fields per `(event, market, selection)`: `ticket_pct`, ideally `handle_pct`, and a `splits_source` + `splits_observed_at`.

### 3.2 Definition (once splits data exists)

```
Let public_side = the selection with the higher ticket_pct (the "public" side).
Let line_dir    = sign(move_prob_open_now) per outcome (Spec §1.2).

RLM is flagged for an event/market when ALL of:
  1. ticket_pct(public_side) ≥ P_rlm                 (lopsided public interest)
  2. the consensus line moved AWAY from public_side:
        move_prob_open_now(public_side) ≤ −D_rlm      (public side got LONGER, less likely)
  3. (strong RLM) handle_pct(public_side) < ticket_pct(public_side)
        → more tickets than money = sharp money on the other side
```

### 3.3 Default thresholds
| Param | Default | Meaning |
|---|---|---|
| `P_rlm` | **≥ 65%** tickets on the public side | lopsided enough to matter (mockup used 71%) |
| `D_rlm` | **≥ 0.015** no-vig prob | the line moved meaningfully against the public |
| handle-vs-ticket gap (strong) | `ticket_pct − handle_pct ≥ 10pts` | money/ticket divergence = sharpest signal |

### 3.4 Worked example (illustrative — requires splits feed)
```
Knicks vs X. Splits feed: 71% of TICKETS on Knicks.
Consensus line: Knicks open p=0.560 → now p=0.535  → move_prob = −0.025 (Knicks got LONGER)
P_rlm: 71% ≥ 65% ✓ ;  D_rlm: 0.025 ≥ 0.015 ✓ (away from public Knicks)
If handle_pct(Knicks)=58% < 71% tickets → strong RLM (sharp money off Knicks).
→ RLM flagged: public on Knicks, line + money moving the other way.
```
(Matches the mockup line: "71% of tickets on Knicks, but the line moved toward the other side.")

### 3.5 Graceful degradation WITHOUT splits (v1 reality)
Until a splits feed is contracted, **we do not fabricate ticket percentages — ever** (that would be a manufactured claim and a compliance violation). Instead:
- **Ship a "Sharp-Move" proxy, clearly labeled as NOT RLM.** Using only prices we *can* compute: a move where **sharp books (`bookmaker.is_sharp = 1`, e.g. Pinnacle/Circa) lead and soft books follow.** See §4. This captures much of the *value* of RLM (where's the sharp money) without claiming to know public ticket %.
- In the UI/report, the RLM card renders in one of two states:
  - **`rlm_available = false`** → show the **Sharp-Move proxy** + an honest note: "Ticket/handle splits not in our current data tier; showing sharp-vs-soft line leadership instead."
  - **`rlm_available = true`** (splits feed live) → show true RLM per §3.2.
- Backend exposes a `splits_source` capability flag so the frontend degrades automatically.

---

## 4. Sharp vs Public Divergence

### 4.1 What we CAN produce on the lean tier: **Sharp-Move / Line-Leadership signal**

We have `bookmaker.is_sharp` and Spec 01 book weights. Define sharp-led movement **without any splits data**:

```
Split books into SHARP (is_sharp=1) and SOFT (is_sharp=0).
Over window Δt:
  δ_sharp = median no-vig prob move across sharp books
  δ_soft  = median no-vig prob move across soft books

SHARP-MOVE flagged when:
  1. |δ_sharp| ≥ M_sharp           (sharp books moved; default 0.020)
  2. sign-consistent across sharp books
  3. LEADERSHIP: sharp move precedes soft move — sharp δ occurs in an earlier
     sub-window than the soft books' matching move (lag ≥ L_lead, default ≥ 60s),
     OR soft books haven't yet caught up (|δ_soft| < |δ_sharp|).
```
This is the honest, price-only version of "sharp action": **the sharp/low-vig books moved first and the soft market is following.** It's the strongest divergence signal available without splits and is genuinely useful for line-shopping (soft books not yet caught up = where +EV lingers, ties straight back to Spec 01 EV).

### 4.2 Thresholds
| Param | Default |
|---|---|
| `M_sharp` | ≥ 0.020 no-vig prob |
| `L_lead` | ≥ 60 s sharp-leads-soft lag |
| min sharp books | ≥ 1 (Pinnacle alone is meaningful); ≥ 2 preferred |

> **The Odds API caveat (flag):** sharp-book coverage is the binding constraint. Pinnacle is only on the `eu` region key (Spec 01 §3.2) and not for all sports; Circa coverage is partial. If **zero** sharp books are available for a market, the Sharp-Move signal **cannot** be produced — degrade to plain consensus movement (§1) and mark `sharp_coverage = none`. Premium feeds give broad sharp coverage + limits, materially improving this signal.

### 4.3 What we CANNOT honestly produce without splits
- True **public betting %** (tickets) → requires splits feed.
- True **handle vs ticket** divergence → requires splits feed.
- "X% of the public is on Y" claims → **never** state these without a real source. Do not infer public % from price alone and present it as fact.

---

## 5. Schema & Compute Requirements (for the Data/Backend Engineer)

### 5.1 Works on The Odds API NOW (price-only signals)
All of these compute from the **existing `odds_snapshot`** table — no schema change needed for the core, only derived compute + a small signals table:

| Signal | Computable now? | Notes |
|---|---|---|
| Opening line capture | ✅ | use `is_opening`; consensus open = first ≥3-book snapshot |
| Open→now / open→close deltas (prob + price) | ✅ | Spec 01 consensus over the series |
| Spread/total **number** moves | ✅ | diff `odds_snapshot.point` over time |
| **Steam** (magnitude/velocity/breadth) | ✅ | needs dense near-event polling (Spec 02 §1.4) |
| **Sharp-Move / line-leadership** | ✅ *(if ≥1 sharp book present)* | uses `bookmaker.is_sharp` |
| **RLM (true)** | ❌ | needs betting-splits feed (§3.1) |
| **Public %, handle vs ticket** | ❌ | needs betting-splits feed |

### 5.2 Recommended derived tables (additive; don't alter `odds_snapshot`)

```sql
-- Per-outcome consensus movement series snapshot (materialized for fast UI).
CREATE TABLE IF NOT EXISTS movement_point (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES event(id),
    market_type_id  INTEGER NOT NULL REFERENCES market_type(id),
    selection       TEXT NOT NULL,
    point           REAL,
    observed_at     TEXT NOT NULL,
    consensus_fair_prob   REAL NOT NULL,     -- Spec 01 §3
    consensus_american    INTEGER NOT NULL,
    n_books         INTEGER NOT NULL,
    confidence      TEXT NOT NULL            -- high|medium|low
);

-- Fired signals (steam / sharp-move / rlm), append-only, auditable.
CREATE TABLE IF NOT EXISTS movement_signal (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES event(id),
    market_type_id  INTEGER NOT NULL REFERENCES market_type(id),
    selection       TEXT NOT NULL,
    point           REAL,
    signal_type     TEXT NOT NULL,           -- 'steam' | 'sharp_move' | 'rlm'
    direction       TEXT NOT NULL,           -- 'toward' | 'away' (relative to selection)
    magnitude_prob  REAL NOT NULL,           -- no-vig prob delta that triggered it
    window_seconds  INTEGER NOT NULL,
    n_books_moved   INTEGER NOT NULL,
    books_total     INTEGER NOT NULL,
    sharp_led       INTEGER,                 -- bool, nullable
    -- RLM-only (NULL until splits feed exists):
    ticket_pct      REAL,
    handle_pct      REAL,
    splits_source   TEXT,
    detected_at     TEXT NOT NULL,
    detail_json     TEXT                     -- thresholds used, per-book deltas
);
CREATE INDEX IF NOT EXISTS idx_movement_signal_event
    ON movement_signal (event_id, signal_type, detected_at);
```

### 5.3 Capability flags the API must expose to the frontend
```
{ "splits_available": false,        // true once a splits feed is contracted
  "sharp_coverage": "partial|none|full",
  "rlm_mode": "true_rlm | sharp_proxy" }
```
The Movement page (`src/pages/Movement.tsx`) and report renderer use these to show true RLM vs the labeled Sharp-Move proxy automatically.

### 5.4 Polling dependency
Steam/sharp velocity need the **near-event poll tightening from Spec 02 §1.4** (down to ~30s near commence). Without dense polling, fast steam is invisible. This is the same credit-limited constraint flagged in Spec 02; on the budget tier, steam detection is "best-effort, coarse-grained" and should be labeled as such.

---

## 6. Frontend / Movement page notes (Fullstack)
- The existing Movement page diffs **raw price** (`o.movement` first vs last). Recommend sourcing the delta from **consensus no-vig prob** (`movement_point.consensus_fair_prob`) so the `▲/▼` reflects true market direction, not a lengthening/shortening price that can mislead (see §1.3 totals example). Keep the American "cents" as a secondary display.
- Add a **signals strip** per event reading `movement_signal` (steam 🔥 / sharp-move / rlm), each with the compliance microcopy already in the page voice ("context, not a signal to chase").
- When `rlm_mode = sharp_proxy`, render the honest "splits not in current tier" note (§3.5).

---

## 7. Summary: the now/later split

**Ships now on The Odds API (price-only, no new data contracts):** opening capture, open→now/close movement in no-vig prob + price, number moves, **steam detection**, and **sharp-move/line-leadership** divergence (where ≥1 sharp book is covered). These power the Movement page and the report's signals block honestly today.

**Needs a paid betting-splits feed + owner approval (later):** true **Reverse Line Movement**, public ticket %, and handle-vs-ticket divergence. Until then we ship the clearly-labeled **Sharp-Move proxy** and **never fabricate public percentages.** A premium odds feed (OddsJam/SportsDataIO) additionally improves steam/sharp accuracy via broad sharp-book coverage and sub-second history.

All signals are probabilistic market observations, presented as context with sample/coverage caveats — consistent with EdgeWire's transparency moat (Specs 01–02) and compliance posture.

---

*Verified numerics: totals Over −110→(+104/−124) → no-vig prob 0.5000→0.4696, Δ=−0.0304. ML steam dog +150/−180 → +120/−145 → no-vig dog prob 0.3836→0.4344, Δ=+0.0508 (5.1 pts), breadth 6/8 in 8 min → steam. Consistent with Spec 01 de-vig (multiplicative) and Spec 02 capture.*
