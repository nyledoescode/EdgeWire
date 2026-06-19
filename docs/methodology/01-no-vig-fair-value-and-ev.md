# Methodology Spec 01 — No-Vig Fair Value & EV Detection

**Owner:** Quant Analyst
**Status:** v1.0 — ready for engineering
**Audience:** Data/Backend Engineer (implementation target), Frontend (display semantics)
**Scope:** How EdgeWire converts raw American odds from multiple sportsbooks into (a) per-book implied probabilities, (b) a vig-free "fair" probability per outcome, (c) a multi-book consensus fair value, and (d) an expected-value (EV) figure per offered price, with +EV thresholding.

> **Compliance note (binding).** Everything in this spec produces *probabilities and EV estimates*, never guarantees. No output of this pipeline may be labeled a "lock," "guaranteed," or carry a manufactured win-rate. Fair value is an **estimate** of the market's consensus true probability and is presented as such. CLV (spec 02) is the auditable accountability layer; EV here is a forward-looking estimate.

---

## 0. Notation & Conventions

- American odds: `A` (e.g. `-110`, `+150`). Always an integer, `|A| ≥ 100`, never in `(-100, +100)` except the degenerate `±100` (even money).
- Decimal odds: `d` (e.g. `1.9091`). `d > 1`.
- Implied probability (raw, with vig): `q`.
- Fair (no-vig) probability: `p`.
- Consensus fair probability across books: `p̄`.
- Stake assumed `= 1` unit unless noted. Profit on a win for decimal `d` is `(d − 1)`.
- All probabilities are in `[0, 1]`. All "percent" outputs are `prob × 100`.
- **Internal representation:** store and compute everything in **decimal odds** and **probabilities**. Convert American → decimal at ingestion; keep the original American string only for display.

---

## 1. American Odds → Decimal → Implied Probability

### 1.1 American → Decimal

```
if A > 0:   d = 1 + A/100
if A < 0:   d = 1 + 100/|A|
```

### 1.2 Decimal → Implied Probability (raw / with vig)

```
q = 1 / d
```

Equivalently, directly from American:

```
if A > 0:   q = 100 / (A + 100)
if A < 0:   q = |A| / (|A| + 100)
```

### 1.3 Probability → Decimal → American (for display / inverse)

```
d = 1 / p
if d >= 2:  A = +(d − 1) * 100        # underdog
if d <  2:  A = -100 / (d − 1)        # favorite
```
Round American to nearest integer for display. Round half away from zero. Never display `A` in `(-100, +100)`; if `d == 2` exactly, display `+100`.

### 1.4 Worked example

`A = -110` → `d = 1 + 100/110 = 1.90909…` → `q = 1/1.90909 = 0.52381` (52.381%).
`A = +150` → `d = 1 + 150/100 = 2.50` → `q = 1/2.50 = 0.40000` (40.000%).

### 1.5 Implementation notes
- Use double-precision floats internally; do **not** round intermediate probabilities. Round only at the display layer (4 decimal places for prob, integer for American).
- Reject/flag any quote with `|A| < 100` (malformed). The Odds API returns decimal `price` for most regions and American for the `us` region — **normalize to decimal at the adapter boundary** so the rest of the pipeline is format-agnostic.

---

## 2. Removing the Vig (De-Vig) → Fair Probability

A market's raw implied probabilities sum to **more than 1**. The excess is the **overround** (a.k.a. vig/juice/hold).

```
overround  M = Σ_i q_i          (sum over all mutually exclusive outcomes i of the market)
hold       H = M − 1            (the book's theoretical margin, as a fraction)
hold %       = H × 100
```

We must distribute that excess back out to recover fair probabilities `p_i` with `Σ p_i = 1`.

### 2.1 Method A — Multiplicative / Proportional (DEFAULT)

Normalize each raw probability by the overround:

```
p_i = q_i / M = q_i / Σ_j q_j
```

This is the **default** EdgeWire de-vig method. It is simple, deterministic, and assumes the book's margin is applied proportionally across outcomes. **Use this everywhere unless a market is flagged for the additive method below.**

**Worked example — 2-way (NFL spread, -110 / -110):**
```
q_home = q_away = 0.52381
M = 1.04762,  H = 0.04762  → 4.762% hold
p_home = 0.52381 / 1.04762 = 0.50000
p_away = 0.52381 / 1.04762 = 0.50000
```
Fair line for each side = `1/0.5 = 2.00` decimal = `+100` American.

**Worked example — 2-way moneyline (-200 / +170):**
```
q_fav = 200/300 = 0.66667
q_dog = 100/270 = 0.37037
M = 1.03704,  H = 3.704% hold
p_fav = 0.66667 / 1.03704 = 0.64286   (fair ≈ -180)
p_dog = 0.37037 / 1.03704 = 0.35714   (fair ≈ +180)
```

**Worked example — 3-way (soccer 1X2, +150 / +220 / +180):**
```
d:  Home 2.50, Draw 3.20, Away 2.80
q:  0.40000, 0.31250, 0.35714
M = 1.06964,  H = 6.964% hold
p_home = 0.40000/1.06964 = 0.37396
p_draw = 0.31250/1.06964 = 0.29216
p_away = 0.35714/1.06964 = 0.33389
(Σ = 1.000)
```

### 2.2 Method B — Additive / Equal-Margin (alternative, favorite-longshot aware-ish)

Subtract an equal share of the hold from each raw probability:

```
p_i = q_i − H/n          where n = number of outcomes
```
This shifts probability mass differently than multiplicative: it implies the book applies the *same absolute* margin per outcome rather than the *same proportional* margin. It compresses favorites less and longshots more relative to multiplicative.

- Can produce `p_i` outside `[0,1]` for extreme markets (huge favorite + tiny longshot). **Guard:** if any `p_i ≤ 0`, fall back to multiplicative.
- Not the default. Offer as a configurable method per sport/market for backtesting.

**2-way -200/+170 via additive:** `H = 0.03704`, `H/2 = 0.01852`. `p_fav = 0.66667 − 0.01852 = 0.64815`, `p_dog = 0.37037 − 0.01852 = 0.35185`. (Note it differs from multiplicative's 0.64286 — favorite gets a *higher* fair prob under additive.)

### 2.3 Method C — Shin's method (advanced; flag for later)

Shin (1992/1993) models the overround as arising from a fraction `z` of insider/informed money and solves for fair probabilities that account for the favorite-longshot bias more rigorously. It requires iteratively solving for `z`:

```
Solve for z in:  Σ_i [ sqrt(z² + 4(1−z) · q_i²/M) − z ] / (2(1−z)) = 1
then  p_i = [ sqrt(z² + 4(1−z)·q_i²/M) − z ] / (2(1−z))
```
- More accurate for markets with strong favorite-longshot bias (big favorites, longshot props). Computationally heavier (Newton-Raphson / bisection, ~5-15 iterations to converge).
- **Defer to v2.** Implement multiplicative now; structure the de-vig function so the method is a strategy parameter (`devig_method ∈ {multiplicative, additive, shin}`) so we can A/B against CLV later without refactoring.

### 2.4 Method D — Power / Logarithmic methods (note only)

`p_i ∝ q_i^k`, solve `k` such that `Σ p_i = 1`. Similar spirit to Shin. Not in scope for v1; same strategy-parameter hook applies.

### 2.5 De-vig method selection (v1 policy)

| Market type | Default method |
|---|---|
| 2-way spreads/totals (-110-ish, balanced) | Multiplicative |
| 2-way moneyline | Multiplicative |
| 3-way (soccer 1X2, etc.) | Multiplicative |
| Player props (2-way over/under) | Multiplicative (see §6) |
| Heavy-favorite moneylines (`p_fav > 0.80`) | Multiplicative, but **log a `favorite_longshot_warn` flag** — these are where Shin would most differ; revisit in v2 |

---

## 3. Multi-Book Consensus Fair Value

A single book's no-vig probability is one noisy estimate of the true probability. We aggregate **across books** to a consensus `p̄` that serves as EdgeWire's reference "fair value."

### 3.1 Pipeline per outcome

1. For each book `b` quoting the market, compute that book's no-vig probability `p_{b,i}` using §2 (de-vig **within each book's own market** — never de-vig across books).
2. Filter the set of `p_{b,i}` (staleness + outliers, §3.3–3.4).
3. Aggregate the surviving `p_{b,i}` into `p̄_i` (§3.2).
4. Renormalize the consensus across outcomes so `Σ_i p̄_i = 1` (the per-book de-vig already removed vig, but cross-book aggregation can leave a tiny residual sum ≠ 1; divide by the sum).

### 3.2 Aggregation function — weighted average (DEFAULT)

```
p̄_i = ( Σ_b w_b · p_{b,i} ) / ( Σ_b w_b )
```

**Book weights `w_b`** (v1 — static, config-driven, tunable later against CLV):

| Tier | Books (examples) | Weight `w_b` |
|---|---|---|
| Sharp / market-setting | Pinnacle, Circa, BetOnline | 3.0 |
| Major efficient | DraftKings, FanDuel, BetMGM, Caesars | 1.5 |
| Other / soft | ESPN BET, Fanatics, regional books | 1.0 |

Rationale: sharp books (esp. **Pinnacle**) have the lowest hold and highest limits, so their no-vig line is the best single estimate of true probability. We over-weight them but still blend so a single book's glitch can't dominate.

> **The Odds API limitation (flag):** Pinnacle is **not** in The Odds API's `us`/`us2` region feeds. It *is* available under the `eu` region key for some sports. The engineer must request the `eu` region to capture Pinnacle where possible. If Pinnacle is unavailable for a given sport/market, the sharpest available book(s) (Circa via some feeds, else the major-efficient tier) become the anchor and the weight table degrades gracefully (weights are applied only to books actually present). **Premium feeds (OddsJam/SportsDataIO) include Pinnacle + limits broadly and at higher refresh rates — this is the single biggest fair-value-accuracy unlock over The Odds API.**

### 3.3 Staleness filter

A quote is **stale** if `now − last_update > τ_sport`. Exclude stale quotes from aggregation.

| Sport / market | `τ` (staleness threshold) |
|---|---|
| Live / in-play | 15 s |
| Pre-game major (NFL/NBA/MLB/NHL mainlines) | 120 s |
| Pre-game props | 300 s |
| Low-volume / futures | 1800 s |

> **The Odds API limitation (flag):** The Odds API exposes a `last_update` timestamp per bookmaker — **use it**, do not assume freshness from poll time. On lower-cost plans poll cadence is limited (rate/credit-bounded), so effective `τ` is constrained by *our* poll interval, not just the threshold. Premium feeds push sub-second/websocket updates → tighter `τ`, viable live-betting screens. With The Odds API, treat sub-60s line movement and live markets as **best-effort, not authoritative**, and surface a "data delay" indicator in the UI for compliance honesty.

### 3.4 Outlier handling

After de-vig and staleness filtering, on the set `{p_{b,i}}` for a single outcome:

1. Compute median `p̃_i` and median absolute deviation `MAD_i = median(|p_{b,i} − p̃_i|)`.
2. Robust z-score: `z_{b} = 0.6745 · (p_{b,i} − p̃_i) / MAD_i` (the 0.6745 makes MAD comparable to σ for normal data).
3. **Exclude** any book with `|z_b| > 3.5` from the consensus aggregation.
4. **Do NOT discard the outlier outright** — an outlier on the *cheap* side (a book offering a much better price than everyone else) is precisely a candidate +EV opportunity. The outlier is removed from the *fair-value computation* (so it doesn't pollute the reference) but is **retained and flagged** as an EV candidate to be evaluated in §4 against the outlier-free consensus.
5. Guard: if `MAD_i == 0` (all books identical) or `< 3` books survive, skip outlier removal and just average what's there. Require **≥ 2 books** to publish a consensus; with 1 book, publish the single de-vigged line but set `consensus_confidence = low` and **suppress EV signals** (can't detect an edge against yourself).

### 3.5 Worked example — consensus from 4 books (NBA moneyline, home side)

Per-book no-vig `p_home` after de-vig:
```
Pinnacle  0.611   w=3.0
DraftKing 0.620   w=1.5
FanDuel   0.618   w=1.5
SoftBookX 0.660   w=1.0   ← far from the pack
```
Median = 0.619, MAD = median(|−0.008|,|0.001|,|−0.001|,|0.041|) = median(0.008,0.001,0.001,0.041)=0.0045.
z(SoftBookX) = 0.6745·(0.660−0.619)/0.0045 = 6.15 > 3.5 → **excluded from fair value**, flagged as EV candidate (SoftBookX implies the home side is a bigger favorite; the *away* side at SoftBookX is the cheap side → check away for +EV).

Consensus over remaining 3:
```
p̄_home = (3.0·0.611 + 1.5·0.620 + 1.5·0.618) / (3.0+1.5+1.5)
       = (1.833 + 0.930 + 0.927) / 6.0
       = 3.690 / 6.0 = 0.6150
```
After computing both outcomes the same way, renormalize so `p̄_home + p̄_away = 1`.

### 3.6 "Fair line" output
The consensus fair probability converts to a fair price for display:
```
fair_decimal = 1 / p̄_i
fair_american = (via §1.3)
```
This is shown as "Fair: -160 (61.5%)" next to each book's offered price.

---

## 4. Expected Value (EV) per Offered Price

Given a book's **offered** decimal price `d_offer` for outcome `i`, and the consensus fair probability `p̄_i`:

### 4.1 Core EV formula (per 1 unit staked)

```
EV_unit = p̄_i · (d_offer − 1) − (1 − p̄_i) · 1
        = p̄_i · d_offer − 1
```

**EV% (return on stake):**
```
EV%  = (p̄_i · d_offer − 1) × 100
```

This is the canonical, preferred output: *expected return per dollar staked.*

### 4.2 Equivalent "edge" framings (compute & store both; display per surface)

- **EV% on stake** (above): `p̄·d − 1`.
- **Probability edge:** `p̄_i − q_offer_i` where `q_offer_i = 1/d_offer` (how much more likely than the book's *implied* (with-vig) price). Useful intuition but conflates vig; prefer EV%.

### 4.3 +EV threshold logic

A bet is flagged **+EV** when:
```
EV% ≥ θ_market
```
Default thresholds (config-driven, tunable):

| Market | `θ` (min EV% to flag) | Rationale |
|---|---|---|
| Major mainlines (NFL/NBA/MLB/NHL ML, spread, total) | **+2.0%** | Tight, efficient; small edges real but noisy |
| Soccer 1X2 / major props | **+3.0%** | Wider markets, more model noise |
| Player props (non-major) | **+4.0%** | Thin, soft, but fair-value estimate noisier |
| Futures / low-liquidity | **+5.0%** | High variance in fair estimate |

Additional gates (ALL must pass to surface a +EV alert):
1. `consensus_confidence ≥ medium` (≥ 3 surviving books, §3.4).
2. Offered quote not stale (§3.3).
3. The offering book is **not** itself the sole basis of the consensus (exclude the offering book from its own fair-value reference — see §4.5).
4. EV computed against the **renormalized, outlier-free** consensus.

### 4.4 Worked example

Consensus fair `p̄_away = 0.385` (from §3, away side). A soft book offers the away side at `+180`:
```
d_offer = 2.80
EV% = (0.385 · 2.80 − 1) × 100 = (1.078 − 1) × 100 = +7.8%
```
`+7.8% ≥ θ(+3.0% props / +2.0% mainline)` → **flag as +EV.** Display: "FanaticsX +180 away · Fair +160 (38.5%) · EV +7.8%."

Counter-example (no edge): same fair `0.385`, book offers `+150` (`d=2.50`):
```
EV% = (0.385·2.50 − 1)×100 = −3.75%  → not flagged (negative EV).
```

### 4.5 Critical: exclude the offering book from its own fair reference

When evaluating book `b`'s price for +EV, recompute (or use a cached) consensus **excluding book b**. Otherwise a soft book that's an outlier drags the consensus toward its own price and *masks* the very edge we want to detect (and conversely a sharp book evaluating against a consensus it dominates understates edges). Implementation: compute the full consensus once, then for each book produce a "leave-one-out" consensus by subtracting that book's weighted contribution:
```
p̄_(−b) = (Σ_all w·p − w_b·p_b) / (Σ_all w − w_b)
```
This is O(1) per book given the full weighted sum. Use `p̄_(−b)` as the fair reference when grading book `b`'s EV.

### 4.6 Kelly stake hint (display-only, optional)

For Elite users we may surface a **fractional Kelly** stake suggestion (full Kelly is too aggressive and not compliant-friendly as "advice"):
```
b = d_offer − 1                      # net decimal payout
f* = (p̄·b − (1 − p̄)) / b = (p̄·d_offer − 1) / (d_offer − 1)
recommended = κ · f*                 # κ = 0.25 (quarter Kelly) default
```
Clamp `recommended` to `[0, 0.05]` (never suggest > 5% of bankroll). Always label as "for educational sizing reference, not advice." Detailed Kelly/confidence-scoring lives in a later spec; this is the hook.

---

## 5. Output Schema (what the engine emits per market/outcome)

Per `(event_id, market_key, outcome, book)` the engine should produce:

```jsonc
{
  "event_id": "...",
  "sport_key": "americanfootball_nfl",
  "market_key": "h2h",                 // h2h | spreads | totals | player_props_*
  "outcome": "home",                   // home|away|draw|over|under|<player+line>
  "book": "fanduel",
  "offered_american": 180,
  "offered_decimal": 2.80,
  "book_last_update": "2026-06-15T...Z",
  "book_no_vig_prob": 0.372,           // this book's own de-vigged prob
  "consensus_fair_prob": 0.385,        // leave-one-out, outlier-free, renormalized
  "consensus_fair_american": 160,
  "consensus_n_books": 5,              // surviving books in the consensus
  "consensus_confidence": "high",      // high(≥5) | medium(3-4) | low(<3)
  "devig_method": "multiplicative",
  "ev_pct": 7.8,
  "prob_edge": 0.043,
  "is_plus_ev": true,
  "ev_threshold_used": 3.0,
  "kelly_quarter": 0.011,
  "flags": ["outlier_excluded_from_fair", "favorite_longshot_warn"],
  "stale": false
}
```

Persist these as a time series (every poll) so spec 02 (CLV) and line-movement features can replay history.

---

## 6. Edge Cases

### 6.1 Stale lines
Covered in §3.3. Stale quotes: excluded from consensus; if the *offered* quote being graded is stale, **do not** emit a +EV alert (the edge may already be gone). Still store the row with `stale: true` for history.

### 6.2 Missing books / thin coverage
- `< 2` books: publish single de-vigged line, `confidence=low`, **no EV signal**.
- `2` books: publish consensus, `confidence=low`, EV signals **suppressed by default** (configurable; risk of grading against a near-empty reference).
- `≥ 3` books: normal operation.

### 6.3 Low-liquidity markets
Wider `τ`, higher `θ` (see tables). Additionally cap displayed Kelly more aggressively and add a `low_liquidity` flag. These are where soft-book outliers are most common and also most likely to be *limited/voided* by the book — surface honestly.

### 6.4 3-way markets (soccer 1X2, and "draw no bet"/double-chance derivatives)
- De-vig across **all three** outcomes (§2.1 example). `M` sums three `q`s.
- Consensus & EV per outcome identically; renormalize over three.
- Derived markets (Double Chance, DNB) should be priced from the de-vigged 1X2 fair probs, **not** de-vigged independently, to stay internally consistent:
  - DNB home fair = `p_home / (p_home + p_away)`
  - Double Chance 1X fair = `p_home + p_draw` (then add a margin only if quoting, never for fair value).

### 6.5 Player props (over/under)
- Treat as a **2-way** market (Over/Under at a line). De-vig the over/under pair within each book (§2.1).
- **Alternate lines:** the same prop exists at multiple lines (e.g. 24.5, 25.5, 26.5 pts). Each `(player, stat, line)` is its **own** market for de-vig/EV. Do not mix lines into one consensus.
- **Coverage problem (flag):** props are where book coverage is thinnest and most divergent. Often only 1–3 books quote a given `(player, line)`. Apply §6.2 strictly. Consensus is weak; lean on §3.4 to still surface clear outliers but mark `confidence=low`.
- **PrizePicks/Underdog (DFS):** these are *not* traditional 2-way books — they offer pick'em at fixed payout multipliers. Fair value for DFS props must be derived from the **sportsbook** consensus prob for that same `(player, stat, line)`, then compared to the DFS implied break-even. This is a distinct sub-spec; for v1, compute the sportsbook-consensus prob and expose it so a later DFS module can grade PrizePicks payouts against it.

> **The Odds API limitation (flag):** Player props on The Odds API require per-event requests (`/events/{id}/odds`) and cost more credits, with **limited book coverage and slower refresh** vs. mainlines. Alternate prop lines are sparse. **Premium feeds (OddsJam/SportsDataIO) unlock far broader prop + alternate-line coverage, DFS (PrizePicks/Underdog) projections, and the granularity to make the props EV screen and DFS value screen genuinely competitive.** With The Odds API, market the props screen as "selected markets," not comprehensive.

### 6.6 Spreads & totals with key-number/half-point context
For v1, grade spreads/totals purely on price EV (§4) at the quoted line. **Line-value** (the value of a better *number*, e.g. +3.5 vs +3) is a separate signal handled in the line-movement/historical spec — flagged here so the engineer knows EV-on-price and line-value are distinct and additive later.

### 6.7 Correlated / non-mutually-exclusive markets
EV math here assumes outcomes within a market are **mutually exclusive and exhaustive** (they de-vig to sum 1). Do not apply the within-market de-vig to outcomes that aren't a complete partition (e.g. a single team total over without its under). Validate at ingestion that a market has its complete set of outcomes before de-vigging; if incomplete, mark `incomplete_market` and skip de-vig/EV (store raw only).

---

## 7. The Odds API vs. Premium Feed — Summary of Limitations

| Capability | The Odds API (budget) | Premium (OddsJam / SportsDataIO) | Impact |
|---|---|---|---|
| Pinnacle / sharp anchor | Partial (`eu` region, not all sports) | Yes, broad | Fair-value accuracy — **biggest gap** |
| Refresh / latency | Poll-based, credit-limited (seconds–minutes effective) | Sub-second / push | Live & sub-minute screens limited on budget |
| Player props coverage | Limited, per-event credit cost | Broad + alternate lines | Props EV screen quality |
| DFS (PrizePicks/Underdog) | Not native | Yes (projections/lines) | DFS value screen blocked on budget |
| Book limits / max bet | No | Often yes | Can't weight by liquidity precisely |
| Historical odds | Limited / extra cost | Yes | CLV & backtests (see spec 02) |

**v1 stance:** ship the full multiplicative de-vig + weighted consensus + EV pipeline on The Odds API now. Anchor on the best sharp book available (request `eu` for Pinnacle where possible). Be transparent in-product about delay and selected-market coverage (compliance + honesty). Architect the de-vig method and book-weight table as config/strategy parameters so upgrading to a premium feed is a data-source swap, not a math rewrite.

---

## 8. Implementation Checklist for the Engineer

1. **Adapter:** normalize every book quote to decimal odds + `last_update`; keep American for display. Reject `|A|<100`.
2. **Market assembler:** group quotes into complete markets `(event, market_key, line)`; validate mutual-exclusivity/completeness before de-vig (§6.7).
3. **De-vig function:** `devig(probs[], method='multiplicative') -> fair_probs[]`. Implement multiplicative + additive now; leave a `shin` stub. Guard additive against ≤0 (§2.2).
4. **Per-book pipeline:** de-vig within each book → store `book_no_vig_prob`.
5. **Consensus:** staleness filter (§3.3) → robust-z outlier filter (§3.4) → weighted average (§3.2) → renormalize (§3.1.4). Compute leave-one-out consensus per book (§4.5).
6. **EV:** `ev_pct = (p̄·d_offer − 1)·100` against leave-one-out consensus; apply gates (§4.3); compute quarter-Kelly hint (§4.6).
7. **Emit** the §5 schema as a time series on every poll.
8. **Config:** book weights, `τ` by sport, `θ` by market, `devig_method`, `κ` — all externalized for tuning against CLV later.

---

*Next spec (02): CLV measurement — uses the consensus-fair / closing-line machinery defined here as the grading reference.*
