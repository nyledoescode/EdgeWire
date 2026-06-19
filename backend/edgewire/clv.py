"""CLV (Closing Line Value) metrics & honest aggregation — Spec 02.

Implements:
  - §2 per-bet CLV metrics: clv_prob (primary), beat_close, clv_pct, clv_cents
  - §3 honest aggregation: BTC rate + Wilson CI, avg CLV% + t-CI, display gates
  - §1 closing-snapshot grading reference uses the Spec 01 consensus (intelligence.py)

Compliance (binding, §3.6): never emit a rate without n + CI; never headline a
sub-30 sample; the all-in aggregate is the headline (no cherry-picking).

Pure functions over plain inputs so the quant's reference vectors (bet -150 vs
close 0.640 -> clv_prob +0.025, clv_pct +6.67%; Wilson 58/100 -> [0.482,0.672])
map directly onto unit tests. The DB grading job lives in clv_grading.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, stdev

from .odds_math import american_to_decimal, decimal_to_american


# =============================================================================
# §2 per-bet CLV metrics
# =============================================================================
@dataclass
class ClvGrade:
    clv_prob: float          # §2.1 p̄_close − p̄_bet (probability delta)
    beat_close: int          # §2.2 1 if bet price beat closing fair price
    clv_pct: float           # §2.3 (d_bet/d_close_fair − 1)·100
    clv_cents: int           # §2.3 american(d_bet) − american(d_close_fair)


def grade_clv(
    bet_decimal: float,
    fair_prob_at_bet: float,
    closing_fair_prob: float,
) -> ClvGrade:
    """Compute all CLV metrics for one graded bet (Spec 02 §2).

    `closing_fair_prob` (p̄_close) and `fair_prob_at_bet` (p̄_bet) are the
    no-vig consensus fair probs from the Spec 01 pipeline at close and at log
    time. `bet_decimal` is the actual price obtained.
    """
    if not 0.0 < closing_fair_prob < 1.0:
        raise ValueError("closing_fair_prob must be in (0,1)")

    d_close_fair = 1.0 / closing_fair_prob

    clv_prob = closing_fair_prob - fair_prob_at_bet
    beat_close = 1 if bet_decimal > d_close_fair else 0
    clv_pct = (bet_decimal / d_close_fair - 1.0) * 100.0
    clv_cents = decimal_to_american(bet_decimal) - decimal_to_american(d_close_fair)

    return ClvGrade(
        clv_prob=clv_prob,
        beat_close=beat_close,
        clv_pct=clv_pct,
        clv_cents=clv_cents,
    )


def grade_clv_american(
    bet_american: int,
    fair_prob_at_bet: float,
    closing_fair_prob: float,
) -> ClvGrade:
    return grade_clv(american_to_decimal(bet_american), fair_prob_at_bet, closing_fair_prob)


# =============================================================================
# §3 honest aggregation
# =============================================================================
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n (§3.2). Default 95%."""
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def t_critical_975(df: int) -> float:
    """t(0.975, df) for the mean CLV% CI (§3.2).

    Small lookup table + normal-approx fallback for large df. Avoids a scipy
    dependency (memory-light). Values are standard two-sided 95% t-criticals.
    """
    table = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
        7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
        20: 2.086, 24: 2.064, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980,
    }
    if df <= 0:
        return float("nan")
    if df in table:
        return table[df]
    # nearest-not-exceeding key, else normal approx (1.96) for large df
    keys = [k for k in table if k <= df]
    if df > 120:
        return 1.96
    return table[max(keys)] if keys else 12.706


def mean_ci(values: list[float]) -> tuple[float, float, float]:
    """Return (mean, lo, hi) 95% t-CI for a list of per-bet CLV% (§3.2)."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0)
    m = mean(values)
    if n == 1:
        return (m, m, m)
    s = stdev(values)
    half = t_critical_975(n - 1) * (s / math.sqrt(n))
    return (m, m - half, m + half)


# §3.3 display gates
def display_gate(n: int, btc_ci_lo: float, avg_clv_ci_lo: float) -> str:
    """Which display tier a track record qualifies for (§3.3).

    Returns: 'building' (<30) | 'small_sample' (30-99) | 'full' (100-499) |
    'verified' (>=500 AND CI lower bounds positive).
    """
    if n < 30:
        return "building"
    if n < 100:
        return "small_sample"
    if n < 500:
        return "full"
    # >=500: 'verified' only if both CI lower bounds clear the bar (§3.3)
    if btc_ci_lo > 0.5 and avg_clv_ci_lo > 0.0:
        return "verified"
    return "full"


@dataclass
class ClvAggregate:
    n: int
    btc_rate: float
    btc_ci95: tuple[float, float]
    avg_clv_pct: float
    avg_clv_pct_ci95: tuple[float, float]
    median_clv_pct: float
    display_gate: str


def aggregate(grades: list[ClvGrade]) -> ClvAggregate:
    """All-in CLV aggregate with mandatory CIs (§3.1–§3.3).

    Pass ONLY graded bets (clv_status='graded'). The all-in number is the
    headline — callers must not pre-filter to flatter the sample (§3.4).
    """
    n = len(grades)
    if n == 0:
        return ClvAggregate(0, 0.0, (0.0, 0.0), 0.0, (0.0, 0.0), 0.0, "building")

    k = sum(g.beat_close for g in grades)
    btc_rate = k / n
    btc_ci = wilson_ci(k, n)

    clv_pcts = sorted(g.clv_pct for g in grades)
    avg, avg_lo, avg_hi = mean_ci(clv_pcts)
    mid = clv_pcts[n // 2] if n % 2 else (clv_pcts[n // 2 - 1] + clv_pcts[n // 2]) / 2

    gate = display_gate(n, btc_ci[0], avg_lo)
    return ClvAggregate(
        n=n,
        btc_rate=btc_rate,
        btc_ci95=btc_ci,
        avg_clv_pct=avg,
        avg_clv_pct_ci95=(avg_lo, avg_hi),
        median_clv_pct=mid,
        display_gate=gate,
    )
