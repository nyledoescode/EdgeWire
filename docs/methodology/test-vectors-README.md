# Methodology Test Vectors — reference fixtures for engineering

**Owner:** Quant Analyst · **For:** Data/Backend Engineer
**File:** `test-vectors.json` (machine-readable) — drop straight into unit tests for the no-vig/EV/CLV/movement math module.

Every value here was computed and verified against Specs 01–03. If your implementation reproduces these numbers (to the stated precision), your de-vig, consensus, EV, CLV, and movement math is correct. Use them as golden fixtures so future refactors can't silently drift.

## What each block tests

| JSON key | Spec | What it checks |
|---|---|---|
| `odds_conversion` | 01 §1 | American → decimal → raw implied prob |
| `decimal_to_american` | 01 §1.3 | inverse conversion + rounding (note `1.5625 → -178`, `1.666667 → -150`) |
| `devig_2way_-110_-110` | 01 §2.1 | multiplicative de-vig, balanced 2-way → 0.5/0.5, 4.7619% hold |
| `devig_2way_-200_+170` | 01 §2.1 | multiplicative de-vig, 2-way ML → 0.642857/0.357143, 3.7037% hold |
| `devig_3way_+150_+220_+180` | 01 §2.1 | 3-way (soccer 1X2) de-vig, sums to 1 |
| `devig_additive_-200_+170` | 01 §2.2 | additive method (differs from multiplicative — favorite gets higher fair) |
| `consensus_nba_home` | 01 §3.2–3.4 | weighted consensus + robust-z (softx z≈6.15 → excluded) → 0.615 |
| `ev_examples` | 01 §4 | EV% = (p·d − 1)·100: +180 → +7.8% (flag), +150 → −3.75% (no flag) |
| `kelly_quarter_p0.385_+180` | 01 §4.6 | quarter-Kelly fraction ≈ 0.010833 |
| `clv_example` | 02 §2 | bet −150 vs close fair 0.640 → CLV_prob +0.025, beat_close true, CLV% +6.6667 (== EV-vs-close), +28 cents |
| `wilson_ci` | 02 §3.2 | Wilson 95% CI: 58/100 → [0.4821, 0.672]; 17/30 → [0.392, 0.7262] |
| `movement_totals_over` | 03 §1.3 | Over −110→(+104/−124) → no-vig prob 0.5→0.46964, Δ −0.030359 |
| `steam_dog_ml` | 03 §2.4 | dog ML +150→+120 → no-vig prob 0.383562→0.434397, Δ +0.050836 → steam |

## Precision notes
- Probabilities: compare to **1e-5** tolerance (vectors rounded to 6 dp).
- Hold/EV/CLV percentages: rounded to 4 dp.
- `decimal_to_american` uses round-half-away-from-zero; American is an integer.
- Do **not** round intermediate values in your pipeline — round only at the display/output boundary (Spec 01 §1.5).

## Regenerate
Vectors were produced by a small deterministic script using only the spec formulas (multiplicative de-vig, weighted consensus, EV, CLV, Wilson). If you change a method (e.g. swap to Shin de-vig), regenerate the affected block and update the spec's worked example to match — keep spec ↔ vectors ↔ code in sync.

Questions on any vector or formula → ping the Quant Analyst.
