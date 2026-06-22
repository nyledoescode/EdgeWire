"""CLV metric & aggregation tests — verified against Spec 02 numerics.

Reference (Spec 02 §2, §3.2): bet -150 (1.6667), p̄_bet 0.615, p̄_close 0.640
-> clv_prob +0.025, beat_close 1, clv_pct +6.67%, clv_cents +28.
Wilson 95%: 58/100 -> [0.482,0.672]; 17/30 -> [0.392,0.726].
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.clv import (
    ClvGrade,
    aggregate,
    display_gate,
    grade_clv_american,
    mean_ci,
    wilson_ci,
)


# ---- §2 per-bet metrics ------------------------------------------------------
def test_grade_clv_reference_vector():
    g = grade_clv_american(-150, fair_prob_at_bet=0.615, closing_fair_prob=0.640)
    assert g.clv_prob == pytest.approx(0.025, abs=1e-6)
    assert g.beat_close == 1
    assert g.clv_pct == pytest.approx(6.67, abs=0.02)
    assert g.clv_cents == pytest.approx(28, abs=1)


def test_no_beat_when_price_worse_than_close():
    # bet at a worse number than the close -> beat_close 0, negative clv_pct
    g = grade_clv_american(-200, fair_prob_at_bet=0.62, closing_fair_prob=0.640)
    assert g.beat_close == 0
    assert g.clv_pct < 0


# ---- §3.2 Wilson CI ----------------------------------------------------------
def test_wilson_58_of_100():
    lo, hi = wilson_ci(58, 100)
    assert lo == pytest.approx(0.482, abs=0.003)
    assert hi == pytest.approx(0.672, abs=0.003)


def test_wilson_17_of_30():
    lo, hi = wilson_ci(17, 30)
    assert lo == pytest.approx(0.392, abs=0.004)
    assert hi == pytest.approx(0.726, abs=0.004)


def test_wilson_includes_50_at_58_100():
    # honesty check: 58/100 CI still includes 0.50 (Spec 02 §3.2)
    lo, hi = wilson_ci(58, 100)
    assert lo < 0.5 < hi


# ---- §3.2 mean CI ------------------------------------------------------------
def test_mean_ci_basic():
    m, lo, hi = mean_ci([6.0, 6.5, 7.0, 6.67, 5.0])
    assert lo < m < hi


# ---- §3.3 display gates ------------------------------------------------------
def test_display_gate_tiers():
    assert display_gate(10, 0.4, -1) == "building"
    assert display_gate(50, 0.45, 1.0) == "small_sample"
    assert display_gate(300, 0.52, 1.0) == "full"
    # >=500 with positive CI lower bounds -> verified
    assert display_gate(600, 0.55, 1.5) == "verified"
    # >=500 but CI includes 50% -> NOT verified
    assert display_gate(600, 0.48, 1.5) == "full"


# ---- aggregate ---------------------------------------------------------------
def test_aggregate_all_in():
    grades = [
        ClvGrade(clv_prob=0.025, beat_close=1, clv_pct=6.67, clv_cents=28),
        ClvGrade(clv_prob=-0.01, beat_close=0, clv_pct=-2.0, clv_cents=-10),
        ClvGrade(clv_prob=0.03, beat_close=1, clv_pct=4.0, clv_cents=15),
    ]
    agg = aggregate(grades)
    assert agg.n == 3
    assert agg.btc_rate == pytest.approx(2 / 3, abs=1e-9)
    assert agg.display_gate == "building"   # n<30
    # CI tuple present and ordered
    assert agg.btc_ci95[0] <= agg.btc_rate <= agg.btc_ci95[1]


def test_aggregate_empty():
    agg = aggregate([])
    assert agg.n == 0
    assert agg.display_gate == "building"
