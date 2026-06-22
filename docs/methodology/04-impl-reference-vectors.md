# Spec 04 — Implementation Reference: Function Signatures & Unit-Test Fixtures

**Owner:** Quant Analyst · **For:** Data/Backend Engineer (critical path: the no-vig/EV/CLV math module)
**Status:** ready to implement — build test-first against the fixtures below.
**Depends on:** Spec 01 (de-vig/consensus/EV), Spec 02 (CLV), Spec 03 (movement). This doc is the *implementation contract*, not new methodology.
**Companion:** `test-vectors.json` (same numbers, machine-readable) + `test-vectors-README.md`.

> Build this as a **new module** alongside the existing `odds_math.py` (which correctly holds mechanical conversions only). Suggested: `edgewire/quant/` — `fairvalue.py` (de-vig + consensus), `ev.py`, `clv.py`, `movement.py`. Keep `odds_math.py` as the conversion primitives these import.

---

## A. Function Signatures (the contract)

Signatures are given in Python type-hint form (the backend is Python). Probabilities are floats in `[0,1]`; never round internally — round only at output (Spec 01 §1.5). `Method` is an enum/string: `"multiplicative"` (default) | `"additive"` | `"shin"` (stub).

### A.1 Conversions (already exist in `odds_math.py` — reuse, don't duplicate)
```python
american_to_decimal(american: int) -> float
decimal_to_american(decimal: float) -> int          # round half away from zero
american_to_implied_prob(american: int) -> float     # RAW (vig-inclusive)
decimal_to_implied_prob(decimal: float) -> float     # = 1/decimal   (add if missing)
```

### A.2 De-vig — `fairvalue.py`
```python
def devig(implied_probs: list[float], method: str = "multiplicative") -> list[float]:
    """Return vig-free fair probabilities that sum to 1.0, in input order.
    multiplicative: p_i = q_i / sum(q)         (DEFAULT)
    additive:       p_i = q_i - (sum(q)-1)/n   (guard: if any p_i<=0, fall back to multiplicative)
    shin:           raise NotImplementedError for v1 (stub the branch)
    Caller must pass a COMPLETE, mutually-exclusive outcome set (Spec 01 §6.7)."""

def market_hold(implied_probs: list[float]) -> float:
    """Overround minus 1 = sum(q) - 1, as a fraction (e.g. 0.04762)."""
```

### A.3 Multi-book consensus — `fairvalue.py`
```python
@dataclass
class BookQuote:
    book_key: str
    fair_prob: float          # this book's de-vigged prob for the outcome (Spec 01 §2)
    weight: float             # from book-weight config (Spec 01 §3.2)
    last_update: datetime     # for staleness (Spec 02 / Spec 01 §3.3)
    is_stale: bool = False

def consensus_fair_prob(
    quotes: list[BookQuote],
    drop_outliers: bool = True,
) -> ConsensusResult:
    """Pipeline (Spec 01 §3.1): filter stale -> robust-z outlier filter (|z|>3.5,
    z = 0.6745*(p-median)/MAD) -> weighted average -> (caller renormalizes across
    outcomes so they sum to 1). Returns consensus prob, surviving n, confidence,
    and the set of excluded book_keys (still surfaced as EV candidates, Spec 01 §3.4)."""

@dataclass
class ConsensusResult:
    fair_prob: float
    n_books: int
    confidence: str           # "high">=5 | "medium"3-4 | "low"<3
    excluded: list[str]

def consensus_leave_one_out(quotes: list[BookQuote], exclude_book: str) -> float:
    """Spec 01 §4.5: consensus excluding `exclude_book`, computed O(1) by subtracting
    that book's weighted contribution from the precomputed weighted sum. This is the
    fair reference used to grade THAT book's offered price for EV."""
```

### A.4 EV — `ev.py`
```python
def ev_pct(fair_prob: float, offer_decimal: float) -> float:
    """Spec 01 §4.1:  (fair_prob * offer_decimal - 1) * 100."""

def is_plus_ev(ev_percent: float, market_key: str, confidence: str, stale: bool) -> bool:
    """Spec 01 §4.3 gates: ev >= theta(market_key) AND confidence>='medium'
    AND not stale. theta from config (mainline +2.0, soccer/major-prop +3.0,
    other prop +4.0, futures +5.0)."""

def quarter_kelly(fair_prob: float, offer_decimal: float, kappa: float = 0.25) -> float:
    """Spec 01 §4.6:  f* = (fair_prob*d - 1)/(d - 1); return clamp(kappa*f*, 0, 0.05)."""
```

### A.5 CLV — `clv.py`
```python
def clv_prob(fair_prob_at_bet: float, closing_fair_prob: float) -> float:
    """Spec 02 §2.1 (PRIMARY):  closing_fair_prob - fair_prob_at_bet."""

def beat_close(bet_decimal: float, closing_fair_prob: float) -> bool:
    """Spec 02 §2.2:  bet_decimal > (1 / closing_fair_prob)."""

def clv_pct(bet_decimal: float, closing_fair_prob: float) -> float:
    """Spec 02 §2.3:  (bet_decimal / (1/closing_fair_prob) - 1) * 100.
    Identity: equals (closing_fair_prob * bet_decimal - 1)*100 = EV-vs-close."""

def clv_cents(bet_american: int, closing_fair_prob: float) -> int:
    """Spec 02 §2.3: bet_american - decimal_to_american(1/closing_fair_prob). Display only."""
```

### A.6 Aggregation stats — `clv.py`
```python
def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Spec 02 §3.2: Wilson score 95% CI for a proportion (beat-the-close rate)."""

def mean_ci_t(values: list[float], conf: float = 0.95) -> tuple[float, float]:
    """Spec 02 §3.2: mean ± t(0.975, n-1) * (s/sqrt(n)) for avg CLV%."""
```

### A.7 Movement / steam — `movement.py`
```python
def move_prob(p_from: float, p_to: float) -> float:
    """Spec 03 §1.2: p_to - p_from (no-vig prob delta; + = toward this outcome)."""

def detect_steam(per_book_deltas: dict[str, float], window_seconds: int,
                 cfg: SteamConfig) -> SteamResult | None:
    """Spec 03 §2.1: ALL of magnitude(|median delta|>=M), velocity(window<=T),
    breadth(frac same-dir>=F and count>=N). Apply false-positive guards (§2.3)
    upstream (stale/outlier/single-book exclusion) before calling."""
```

---

## B. Unit-Test Fixtures (inputs → expected outputs)

**Tolerances:** probabilities to `1e-5`; percentages to `1e-4`; American odds exact integer. Do **not** round intermediates. All values below are verified.

### B.1 Odds conversion (Spec 01 §1)
| american | → decimal | → raw implied_prob |
|---|---|---|
| -110 | 1.909091 | 0.523810 |
| +150 | 2.500000 | 0.400000 |
| -200 | 1.500000 | 0.666667 |
| +120 | 2.200000 | 0.454545 |

decimal → american (round half away from zero):
| decimal | → american |
|---|---|
| 1.909091 | -110 |
| 2.500000 | +150 |
| 1.562500 | -178 |
| 1.666667 | -150 |

### B.2 De-vig (Spec 01 §2)
| input (American pair/triple) | method | → fair probs | hold % |
|---|---|---|---|
| -110 / -110 | multiplicative | [0.500000, 0.500000] | 4.7619 |
| -200 / +170 | multiplicative | [0.642857, 0.357143] | 3.7037 |
| +150 / +220 / +180 (3-way) | multiplicative | [0.373957, 0.292154, 0.333890] | 6.9643 |
| -200 / +170 | additive | [0.648148, 0.351852] | (same hold) |

*Note: additive gives the favorite a **higher** fair prob (0.648148) than multiplicative (0.642857) — they must differ; if your additive == multiplicative, the method isn't wired.*

### B.3 Consensus + outlier exclusion (Spec 01 §3) — NBA home
Input books (book, de-vig fair_prob, weight):
`pinnacle 0.611 w3.0 · draftkings 0.620 w1.5 · fanduel 0.618 w1.5 · softx 0.660 w1.0`
| step | expected |
|---|---|
| median | 0.619 |
| MAD | 0.0045 |
| robust-z (softx) | ≈ 6.1454 → `|z|>3.5` → **excluded** |
| robust-z (others) | pinnacle ≈ -1.1991, draftkings ≈ 0.1499, fanduel ≈ -0.1499 → all kept |
| consensus over kept 3 | **0.615000** |
| confidence | **"medium"** (3 surviving books; Spec 01 §3 table: medium = 3–4) |

*(Excluded `softx` is retained as an EV candidate, Spec 01 §3.4 — not discarded.)*

### B.4 Leave-one-out consensus + EV (Spec 01 §4.5) — clean 4-book set
Input books (home fair_prob, weight): `pinnacle 0.611 w3.0 · draftkings 0.620 w1.5 · fanduel 0.618 w1.5 · caesars 0.624 w1.5`
| quantity | expected |
|---|---|
| full consensus (all 4) | 0.616800 |
| leave-one-out excluding fanduel | **0.616500** (identical via O(1) subtraction) |
| grade fanduel home @ -140 (dec 1.714286) vs LOO 0.6165 | **EV = +5.6857%** |

### B.5 EV (Spec 01 §4) — fair_prob = 0.385
| offer american | offer decimal | → EV% | +EV @ θ=3.0? |
|---|---|---|---|
| +180 | 2.800000 | +7.8000 | true |
| +150 | 2.500000 | -3.7500 | false |

Quarter-Kelly (`fair=0.385, +180`): **0.010833** (clamped range [0, 0.05]).

### B.6 CLV (Spec 02 §2) — bet -150, p_bet 0.615, p_close 0.640
| metric | formula | expected |
|---|---|---|
| d_bet | a2d(-150) | 1.666667 |
| d_close_fair | 1/0.640 | 1.562500 |
| clv_prob | 0.640 - 0.615 | **+0.025000** |
| beat_close | 1.666667 > 1.562500 | **true** |
| clv_pct | (1.666667/1.5625 - 1)*100 | **+6.6667** |
| ev_vs_close% (identity check) | (0.640*1.666667 - 1)*100 | **+6.6667** (must equal clv_pct) |
| clv_cents | -150 - (-178) | **+28** |

### B.7 Aggregation CIs (Spec 02 §3.2)
| k / n | Wilson 95% CI |
|---|---|
| 58 / 100 | [0.4821, 0.6720] |
| 17 / 30 | [0.3920, 0.7262] |

### B.8 Movement / steam (Spec 03)
| case | input | expected |
|---|---|---|
| totals Over move | open -110/-110 → now +104/-124 | p_open 0.500000, p_now 0.469641, **Δ -0.030359** |
| dog ML steam | +150/-180 → +120/-145, 6/8 books, 8 min | p 0.383562 → 0.434397, **Δ +0.050836**, breadth 6/8 ≥0.6, window 8≤10 → **steam=true** |

---

## C. Suggested test order (build sequence on the critical path)
1. `decimal_to_implied_prob` + round-trip conversions (B.1) — trivial, unblocks everything.
2. `devig(multiplicative)` (B.2 rows 1–3) → then `additive` (B.2 row 4, assert it differs).
3. `consensus_fair_prob` with outlier filter (B.3) → `consensus_leave_one_out` (B.4).
4. `ev_pct` + `is_plus_ev` + `quarter_kelly` (B.5) — this is the "intelligence" payload.
5. `clv_*` (B.6) incl. the EV-vs-close identity assertion.
6. `wilson_interval` (B.7); movement/steam (B.8) last.

Get 1–4 green and the EV screen has real numbers end-to-end. Ping me on any fixture that won't reconcile — a mismatch is either a method bug or a spec ambiguity I should fix, and I want to know either way.

---

*All fixtures verified by the Quant Analyst against Specs 01–03 formulas. Mirror in `test-vectors.json`.*
