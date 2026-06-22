# Methodology Spec 02 — Closing Line Value (CLV) Measurement

**Owner:** Quant Analyst
**Status:** v1.0 — ready for engineering
**Depends on:** Spec 01 (No-Vig Fair Value & EV Detection) — reuses its de-vig (§2), multi-book consensus (§3), and odds-conversion (§1) machinery verbatim. Read Spec 01 first.
**Audience:** Data/Backend Engineer (schema + capture rules), Growth Lead (what we can/can't claim), Frontend (display semantics).
**Scope:** How EdgeWire captures the **closing line**, computes **Closing Line Value (CLV)** for a logged bet/signal, and aggregates CLV **honestly** across a track record as our auditable trust moat.

> **Compliance note (binding).** CLV is a **process metric**, not an outcome guarantee. Beating the closing line is the most reliable available *leading indicator* that a bet was placed at a genuine edge — but it does **not** guarantee profit on any individual bet or any sample. We present CLV with sample sizes and confidence intervals, we never convert it into a "win rate" or a guaranteed-return claim, and we never cherry-pick segments. This is the whole point of the metric: honest, auditable accountability. See §4 for the claim policy.

---

## 0. Why CLV

A sportsbook's **closing line** is the market's final, sharpest consensus right before an event starts — it has absorbed all bets, news, lineup/weather info, and sharp money. Across large samples it is the best public estimate of true probability available. If you systematically obtain prices **better than the closing fair value**, you were systematically betting at positive expected value, regardless of how any single game landed. EdgeWire's promise ("the intelligence works") is provable *only* through CLV, because raw win/loss over any tractable sample is dominated by variance.

**Key principle:** we measure CLV against the **no-vig consensus closing fair probability** (Spec 01 §3), *not* against a single book's raw closing price. A single book's closing number still contains vig and book-specific bias; the consensus no-vig closing line is our clean reference.

---

## 1. The Closing Line: Definition & Capture

### 1.1 Definitions

- **`t_event`** — scheduled event start time (from the schedule/odds feed), in UTC.
- **Per-book closing price** `d_close^(b)` — the **last non-suspended** price book `b` quoted for the outcome strictly before `t_event`, subject to the freshness rule below.
- **Consensus closing fair probability** `p̄_close` — apply Spec 01's full pipeline (de-vig within each book §2 → staleness filter → robust-z outlier filter → weighted consensus §3 → renormalize) to the **closing snapshot** of quotes. This is the grading reference for CLV.
- **Bet/signal fair probability** `p̄_bet` — the consensus fair probability at the moment the bet was logged (Spec 01 §3, the same leave-one-out-aware value already stored on the EV signal).
- **Bet price** `d_bet` — the actual decimal odds the user got (or, for a pure EdgeWire signal with no user stake, the offered price that triggered the signal).

### 1.2 Capture timing rule (the "close")

Because we poll (not stream), define the close as a **capture window**, not an instant:

```
closing snapshot = the last poll for which, per book,
                   last_update ∈ [t_event − W_capture, t_event)
                   AND the market is not suspended/settled.
```

| Sport / market | `W_capture` (look-back window for "closing" quotes) |
|---|---|
| Major mainlines (NFL/NBA/MLB/NHL ML/spread/total) | 10 min |
| Soccer 1X2 | 10 min |
| Player props | 20 min (props firm up later, but coverage thins; widen) |
| Low-volume / futures | N/A — CLV not meaningful (see §1.5) |

Rule of capture:
1. For each book, take its **latest** quote whose `last_update` falls in the window and is not suspended.
2. If a book has **no** in-window quote (e.g. it stopped updating 30 min before tip), it is **excluded** from the closing consensus — do not carry a stale pre-window price forward into the close.
3. Build `p̄_close` from the surviving books via Spec 01 §3 (same weights, same outlier filter). Record `n_books_close`.
4. Require **≥ 3 surviving books** for a `high`-confidence close; 2 books = `low`; <2 = **CLV ungraded** for that bet (store the bet, mark `clv_status = ungraded_no_close`).

### 1.3 Handling books that pull / suspend the market

- **Suspended at close (no in-window quote):** exclude from `p̄_close` (rule 2 above). Do **not** treat a suspension as a price.
- **The book the user bet at pulls the market:** CLV is graded against the **consensus** `p̄_close`, which does not require the user's specific book to still be open. This is a feature — consensus closing fair value is book-independent. Record `bet_book_open_at_close` (bool) for diagnostics but it does not block grading.
- **Whole market voided / postponed (event doesn't start at `t_event`):** mark `clv_status = ungraded_postponed`; re-grade against the rescheduled `t_event` if the event is replayed, else drop from CLV (and from any win/loss record — a void is a push).
- **Line/number changed (spreads/totals):** CLV on spreads/totals must compare **like-for-like on price at a given number**, plus a separate line-value component. v1 grades **moneyline and totals/spreads price CLV at the bet's number** by interpolating the closing price *at that same number* when the book offers alternates; if the exact number isn't available at close, fall back to the **probability-delta** method (§2.3), which is number-agnostic because it works in fair-probability space. (Full key-number line-value modeling is deferred to the line-movement spec.)

### 1.4 Snapshot cadence near close

To actually capture a good "close," polling must **tighten** as `t_event` approaches. Recommended cadence (engineer — see §5 schema/capture requirements):

| Time to `t_event` | Poll interval (pre-game mainlines) |
|---|---|
| > 6 h | per existing baseline (e.g. 5–15 min) |
| 60–6 h... 60 min | 5 min |
| 60–10 min | 60–90 s |
| 10–0 min | **30 s (as fast as credits allow)** |

> **The Odds API limitation (flag):** poll cadence is credit-limited. The true market close can move in the final seconds; a 30–90 s poll means our captured "close" is an **approximation** of the real closing number, and it lags fast late steam. This biases measured CLV slightly (usually *understates* CLV for bets that beat a late move, and can misclassify marginal beats). **Premium feeds (OddsJam/SportsDataIO) stream sub-second updates and publish an explicit closing line, giving a far more precise and less biased close** — the single biggest accuracy unlock for CLV. v1 stance: capture the best close we can, label CLV "consensus close (polled)" in-product for honesty, and store enough snapshots (§5) to recompute if we upgrade feeds.

### 1.5 When CLV is NOT meaningful
Futures, season-long, and ultra-thin markets have no sharp "close" in the same sense (and often no event-start de-correlation). Mark these `clv_not_applicable`; do not include them in CLV aggregates. Be explicit in the UI.

---

## 2. CLV Metric Definitions (with worked examples)

All worked examples below are **numerically consistent with Spec 01 §3.5**: the NBA game where the home side's consensus fair probability was **`p̄ = 0.615`** (fair price −160).

**Scenario for §2:** A user (or EdgeWire signal) takes **HOME at −150** (`d_bet = 1.6667`) when the consensus fair was `p̄_bet = 0.615`. Sharp money then backs home; by tip the consensus closing fair is **`p̄_close = 0.640`** (fair price ≈ −178). The market moved *toward* the bet → positive CLV.

### 2.1 CLV as a no-vig probability delta (PRIMARY, number-agnostic)

```
CLV_prob = p̄_close − p̄_bet
```
This is the cleanest, most robust CLV measure: how much more probable the bet's outcome looked at the close vs. when bet, in vig-free terms. Positive ⇒ market moved your way ⇒ you got a price the market later agreed was too generous.

**Worked example:**
```
CLV_prob = 0.640 − 0.615 = +0.025   (+2.5 percentage points of fair probability)
```

### 2.2 Beat-the-Close (binary)

A bet **beats the close** if the price obtained is better than the closing **fair** price for that outcome:

```
beat_close = 1  if  d_bet > d_close_fair      (decimal: higher = better price)
             0  otherwise
where d_close_fair = 1 / p̄_close
```
Equivalently in probability space: `beat_close = 1 if (1/d_bet) < p̄_close` (your bet's implied break-even prob is below the closing fair prob).

**Worked example:**
```
d_close_fair = 1 / 0.640 = 1.5625   (≈ −178 American)
d_bet = 1.6667 (−150)
1.6667 > 1.5625  → beat_close = 1  ✓
```
You locked −150 on a side that closed at a −178 fair value. Clear beat.

> **No-vig on both sides.** `d_bet` is the *actual* (with-vig) price you got, but `d_close_fair` is the *no-vig* closing reference. This is deliberate and standard: it asks "did I beat where the true market closed?" If instead you want a vig-neutral, apples-to-apples view, also compute the bet's own no-vig-equivalent (Spec 01 §2 within the bet snapshot) — store both; default display uses `d_bet` vs `d_close_fair` as above.

### 2.3 Average CLV in percent (price-based) and "cents"

**Percentage CLV (return-space):**
```
CLV_pct = (d_bet / d_close_fair − 1) × 100
```
This is the percentage by which your price beat the closing fair price.

**Worked example:**
```
CLV_pct = (1.6667 / 1.5625 − 1) × 100 = +6.67%
```

**Identity worth noting (sanity check):** `CLV_pct` equals the **EV measured against the closing fair probability**:
```
EV_vs_close% = (p̄_close · d_bet − 1) × 100 = (0.640 · 1.6667 − 1) × 100 = +6.67%
```
These coincide because `p̄_close = 1/d_close_fair`. So **price-based CLV% and "EV against the closing line" are the same number** — we report it as CLV% and note it is the realized-edge proxy. (This is the honest link between Spec 01's forward EV and Spec 02's backward-looking CLV: EV is estimated against the *current* consensus; CLV re-grades that same bet against the *closing* consensus, which is a better truth proxy.)

**"Cents" CLV (American-odds parlance):** the difference between bet American odds and closing-fair American odds, in points. Useful colloquial display for US users:
```
CLV_cents = american(d_bet) − american(d_close_fair)     # signed, "cents" = American points
          = (−150) − (−178) = +28 cents
```
Report `CLV_cents` only as a display convenience; aggregate analytics use `CLV_prob` and `CLV_pct` (cents are non-linear in probability and unsafe to average).

### 2.4 "Percentage-of-edge captured" (optional, advanced)
If a signal was flagged at forward EV `EV_bet%` (Spec 01 §4) and it realized `CLV_pct` against the close, the fraction of the predicted edge that the market confirmed is:
```
edge_capture_ratio = CLV_pct / EV_bet%      (cap display to [−2, +2]; it's noisy per-bet)
```
Meaningful only in aggregate; do not show per-bet as a headline.

### 2.5 Which metric is canonical
- **`CLV_prob`** (probability delta, §2.1) — primary for aggregation; number-agnostic and robust to vig.
- **`beat_close`** (§2.2) — primary for the headline "beat-the-close rate."
- **`CLV_pct`** (§2.3) — the realized-edge proxy; primary for "average CLV %."
- `CLV_cents` — display only.

---

## 3. Honest Aggregation Across a Track Record

### 3.1 The two headline aggregates

**Beat-the-close rate** over `n` graded bets:
```
BTC_rate = (Σ beat_close) / n
```

**Average CLV %** (equal-weighted across bets):
```
avg_CLV_pct = (Σ CLV_pct_i) / n
```
Also report **average `CLV_prob`** (in percentage points) — it's the least-distorted central tendency. Use the **median** alongside the mean for `CLV_pct` because a few large-odds beats can skew the mean.

### 3.2 Sample-size caveats & confidence intervals (MANDATORY on every aggregate)

CLV rates are noisy. **Never display a beat-the-close rate without a confidence interval and `n`.**

**Beat-the-close rate → Wilson score interval** (better than normal approximation for proportions, especially small/extreme `n`):
```
Given k beats in n bets, p̂ = k/n, z = 1.96 (95%):
center = (p̂ + z²/2n) / (1 + z²/n)
half   = ( z·√( p̂(1−p̂)/n + z²/4n² ) ) / (1 + z²/n)
CI95   = [center − half, center + half]
```

**Worked example — 58 beats in 100 bets:**
```
p̂ = 0.58
Wilson 95% CI ≈ [0.482, 0.672]
```
→ We display: **"Beat the close 58% (95% CI 48–67%, n=100)."** Note the CI still includes 50% at n=100 — we say so honestly rather than claiming a proven edge.

**Same 58% but n=30 (17/30):**
```
Wilson 95% CI ≈ [0.392, 0.726]
```
→ Far wider; at n=30 we explicitly label the track record **"insufficient sample — directional only."**

**Average CLV % → t-based CI on the mean:**
```
CI95(avg_CLV_pct) = mean ± t(0.975, n−1) · (s / √n)
where s = sample std dev of per-bet CLV_pct.
```
Display mean CLV% with this CI and `n`.

### 3.3 Minimum-sample display gates

| `n` graded bets | What we display |
|---|---|
| `< 30` | "Building track record" — show raw numbers, **no rate claims**, flagged directional-only |
| `30–99` | Show BTC rate + Wilson CI + explicit "small sample" caveat |
| `100–499` | Show full aggregates with CIs |
| `≥ 500` | Full aggregates; eligible for headline "verified CLV" framing **only if CI lower bound > 50%** |

A positive CLV edge is only claimed as "evidenced" when the **Wilson CI lower bound for BTC_rate is strictly above 50%** *and* `avg_CLV_pct` CI lower bound `> 0`. Otherwise we report the numbers neutrally as a track-in-progress.

### 3.4 Segmentation (and its trap)

Segment CLV by **sport, market type, bet tier (mainline vs prop), odds bucket, and signal type** — this is genuinely informative (e.g. "our prop signals beat the close, our futures don't"). **But:**
- **No cherry-picking.** The *headline* CLV is always the **all-in, every-graded-bet** aggregate. Segment views are secondary and must show their own `n` + CI.
- **Multiple-comparisons honesty.** With many segments, some will look great by chance. Do not promote a flattering thin segment to marketing. Apply the §3.3 gates **per segment** and never headline a segment with `n < 100`.
- Store every graded bet immutably (§5) so the all-in number can never be quietly re-based.

### 3.5 Weighting
Default aggregates are **equal-weighted per bet** (one bet = one observation) — simplest and hardest to game. Optionally compute a **stake-weighted** CLV for users who size with Kelly, but keep equal-weighted as the published headline (stake-weighting can be gamed by oversizing the good ones).

### 3.6 What we WILL and WON'T claim (compliance — share with Growth Lead)

**WILL:**
- "Across N graded bets, EdgeWire signals beat the closing line X% of the time (95% CI a–b%)."
- "Average CLV of +Y% (95% CI c–d%) over N bets, all signals included."
- "CLV is a measure of *process quality* — getting prices the market later moved past — not a guarantee of profit."
- Show the full, immutable, segmented ledger on request (auditability = the moat).

**WON'T:**
- Quote a beat-the-close rate or CLV without `n` and a CI.
- Convert CLV into an implied/"expected" win rate or ROI guarantee.
- Headline any cherry-picked segment, hot streak, or sub-30 sample.
- Hide losing segments or re-base the denominator.
- Use the word "guaranteed," or any manufactured win-rate, anywhere near CLV.

---

## 4. Backend Schema & Capture Requirements (for the Data/Backend Engineer)

CLV grading is **only as good as the snapshots stored.** The pipeline must persist enough to (a) reconstruct the closing consensus and (b) re-grade if we change methods or upgrade feeds. Required:

### 4.1 Odds time-series (already needed for Spec 01) — must retain through `t_event`
Per poll, per `(event_id, market_key, line, outcome, book)`:
- `captured_at` (UTC, our poll time), `book_last_update` (UTC, from the feed — **store both**; freshness uses `book_last_update`).
- `offered_decimal`, `offered_american`, `is_suspended` (bool).
- `event_start_utc` (`t_event`), updated if the schedule changes.
- Derived per Spec 01: `book_no_vig_prob`, and the snapshot's `consensus_fair_prob` + `n_books` + `confidence`.

**Retention:** keep the full per-poll series at least from `t_event − 6h` through `t_event` (denser near close per §1.4). Coarser sampling acceptable earlier. Never delete the in-window (`W_capture`) snapshots — they ARE the close.

### 4.2 Bet/Signal log (the gradable record) — immutable, append-only
Per logged bet or EdgeWire signal:
```jsonc
{
  "bet_id": "...",
  "user_id": "... | null(for pure signal)",
  "event_id": "...", "sport_key": "...", "market_key": "...", "line": -1.5,
  "outcome": "home",
  "logged_at_utc": "...",           // when the bet/signal was recorded
  "bet_book": "fanduel",
  "bet_decimal": 1.6667, "bet_american": -150,
  "fair_prob_at_bet": 0.615,        // Spec 01 consensus (leave-one-out) at log time
  "ev_pct_at_bet": 4.0,             // Spec 01 forward EV at log time (if signal)
  // ---- filled at grading (post-close) ----
  "event_start_utc": "...",
  "closing_consensus_fair_prob": 0.640,
  "closing_fair_american": -178,
  "n_books_close": 5, "close_confidence": "high",
  "bet_book_open_at_close": true,
  "clv_prob": 0.025,                // §2.1
  "beat_close": true,               // §2.2
  "clv_pct": 6.67,                  // §2.3
  "clv_cents": 28,                  // display
  "clv_status": "graded",           // graded | ungraded_no_close | ungraded_postponed | clv_not_applicable
  "devig_method": "multiplicative", // method used (for reproducibility)
  "graded_at_utc": "..."
}
```
- **Append-only / immutable:** never overwrite a graded bet's CLV in place. If a regrade is needed (method change, feed upgrade), write a **new versioned row** and keep the old — auditability requires the original.
- `clv_status` must be set even when ungradable so aggregates can correctly exclude them with a documented reason.

### 4.3 Grading job
A scheduled job runs shortly after each `t_event` (e.g. `t_event + 15 min`, after results/closes settle):
1. Build the closing snapshot (§1.2) from the retained time-series.
2. Compute `p̄_close` via Spec 01 §3.
3. For every bet on that event with `clv_status` unset, compute §2 metrics and write the grading fields.
4. Set `clv_status` appropriately; emit to the CLV aggregate store.

### 4.4 Aggregate store
Materialize rolling aggregates (all-in + per segment) with `n`, `BTC_rate`, Wilson CI, `avg_CLV_pct` + t-CI, median CLV%. Recompute on each grading batch. The §3.3 display gates are enforced at the API/UI layer reading this store.

### 4.5 The Odds API limitation (flag, again, concretely)
- We store `book_last_update`; if the feed's own timestamp is coarse or lags, our "close" is correspondingly imprecise.
- Credit limits cap how dense the near-close polling (§1.4) can be → captured close approximates the true close → small, mostly conservative bias in measured CLV.
- No native "official closing line" field → we **construct** the close from polls. **Premium feeds expose an explicit closing line + sub-second history → more precise, less biased, less storage burden on us.** Architect grading to read from our time-series so swapping in a premium closing-line field later is a capture-layer change, not a metric rewrite.

---

## 5. Implementation Checklist (Engineer)

1. Add **near-close poll-cadence tightening** (§1.4) keyed off `event_start_utc`.
2. Retain per-poll odds time-series through `t_event`, never dropping in-window (`W_capture`) snapshots (§4.1).
3. Implement the **closing snapshot builder** (§1.2): in-window, non-suspended, per-book latest → Spec 01 §3 consensus → `p̄_close`, `n_books_close`, confidence.
4. Implement the **bet/signal log** (append-only, §4.2) capturing `fair_prob_at_bet` from the Spec 01 pipeline at log time.
5. Implement the **grading job** (§4.3): compute `clv_prob`, `beat_close`, `clv_pct`, `clv_cents`; set `clv_status`.
6. Implement the **aggregate store** (§4.4) with Wilson CI (BTC rate) and t-CI (avg CLV%), all-in + segmented, with `n`.
7. Enforce **display gates** (§3.3) and the **claim policy** (§3.6) at the API/UI boundary.
8. Keep `devig_method` + book weights as config (Spec 01 §8) so regrades are reproducible and versioned.

---

## 6. Summary: The Honest Trust Moat
CLV, measured against the **no-vig consensus closing line**, is the one metric that proves EdgeWire's intelligence finds real edges without resorting to variance-driven win-rate claims. We compute it rigorously (probability-delta primary, price-CLV and beat-the-close alongside), we report it with sample size and confidence intervals **always**, we never cherry-pick segments, and we keep an immutable, auditable ledger. The biggest accuracy constraint is The Odds API's poll-based close approximation; a premium feed's explicit closing line is the upgrade path, and the schema is built so that upgrade is a capture-layer swap, not a methodology change.

---

*Verified numerics (consistent with Spec 01 §3.5, p̄=0.615): bet −150 (1.6667), close fair 0.640 (−178) → CLV_prob +0.025, beat_close=1, CLV_pct +6.67% (= EV vs close +6.67%), CLV_cents +28. Wilson 95% CI: 58/100 → [0.482, 0.672]; 17/30 → [0.392, 0.726].*
