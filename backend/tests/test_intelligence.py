"""Spec 01 intelligence-engine tests — verified against the quant's reference
numerics (Spec 01 §1.4, §2.1, §3.5, §4.4). These vectors are the contract;
the quant reviews them for numerical correctness before submit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.intelligence import (
    BookQuote,
    consensus,
    devig,
    devig_american,
    ev_pct,
    ev_pct_american,
    implied_prob,
    leave_one_out_prob,
    prob_to_american,
    quarter_kelly,
    renormalize,
    is_plus_ev,
)


# ---- §1 conversions ----------------------------------------------------------
def test_implied_prob_minus_110():
    assert implied_prob(-110) == pytest.approx(0.52381, abs=1e-5)


def test_implied_prob_plus_150():
    assert implied_prob(150) == pytest.approx(0.40000, abs=1e-5)


def test_prob_to_american_even():
    assert prob_to_american(0.5) == 100


# ---- §2.1 multiplicative de-vig ---------------------------------------------
def test_devig_2way_balanced():
    # -110 / -110 -> 0.5 / 0.5
    p = devig_american([-110, -110])
    assert p[0] == pytest.approx(0.5, abs=1e-6)
    assert p[1] == pytest.approx(0.5, abs=1e-6)


def test_devig_2way_moneyline():
    # -200 / +170 -> 0.64286 / 0.35714 (Spec 01 §2.1)
    p = devig_american([-200, 170])
    assert p[0] == pytest.approx(0.64286, abs=1e-5)
    assert p[1] == pytest.approx(0.35714, abs=1e-5)


def test_devig_3way_soccer():
    # +150 / +220 / +180 -> 0.37396 / 0.29216 / 0.33389 (Spec 01 §2.1)
    p = devig_american([150, 220, 180])
    assert p[0] == pytest.approx(0.37396, abs=1e-4)
    assert p[1] == pytest.approx(0.29216, abs=1e-4)
    assert p[2] == pytest.approx(0.33389, abs=1e-4)
    assert sum(p) == pytest.approx(1.0, abs=1e-9)


def test_devig_additive_favorite_higher():
    # Spec 01 §2.2: additive gives favorite a HIGHER fair prob than multiplicative.
    mult = devig_american([-200, 170], method="multiplicative")
    add = devig_american([-200, 170], method="additive")
    assert add[0] > mult[0]


def test_devig_shin_stub_raises():
    with pytest.raises(NotImplementedError):
        devig([0.6, 0.45], method="shin")


# ---- §3.5 weighted consensus + outlier ---------------------------------------
def _nba_home_quotes():
    # Spec 01 §3.5: per-book no-vig p_home already given; build market pairs that
    # de-vig to those values by pairing each with its complement (no vig in pair).
    def pair(p_home):
        # construct american prices whose multiplicative de-vig returns ~p_home;
        # simplest: a vig-free pair (q sums to 1) so de-vig is identity.
        from edgewire.odds_math import decimal_to_american
        d_home = 1.0 / p_home
        d_away = 1.0 / (1.0 - p_home)
        return [decimal_to_american(d_home), decimal_to_american(d_away)]

    return [
        BookQuote("pinnacle", pair(0.611), 0, is_sharp=True),
        BookQuote("draftkings", pair(0.620), 0),
        BookQuote("fanduel", pair(0.618), 0),
        BookQuote("softbookx", pair(0.660), 0),  # far from pack -> outlier
    ]


def test_consensus_excludes_outlier_and_weights():
    res = consensus(_nba_home_quotes())
    assert "softbookx" in res.excluded_books
    # Weighted over the 3 survivors: (3*.611 + 1.5*.620 + 1.5*.618)/6 = 0.6150
    assert res.fair_prob == pytest.approx(0.6150, abs=1e-3)
    assert res.n_books == 3
    assert res.confidence == "medium"


def test_renormalize_sums_to_one():
    home = consensus(_nba_home_quotes())
    # away side: complements ~ symmetric; just assert renorm sums to 1
    away = consensus([
        BookQuote("pinnacle", [prob_to_american(0.389)] + [prob_to_american(0.611)], 0, is_sharp=True),
    ])
    probs = renormalize([home, away])
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)


# ---- §4 EV ------------------------------------------------------------------
def test_ev_plus():
    # fair 0.385, offered +180 (d=2.80) -> EV +7.8% (Spec 01 §4.4)
    assert ev_pct_american(0.385, 180) == pytest.approx(7.8, abs=0.1)


def test_ev_negative_counterexample():
    # fair 0.385, offered +150 (d=2.50) -> -3.75% (Spec 01 §4.4)
    assert ev_pct_american(0.385, 150) == pytest.approx(-3.75, abs=0.01)


def test_leave_one_out_drops_book():
    res = leave_one_out_prob(_nba_home_quotes(), "softbookx")
    # softbookx removed entirely; consensus over remaining 3 ~ 0.6150
    assert "softbookx" not in res.per_book
    assert res.fair_prob == pytest.approx(0.6150, abs=1e-3)


def test_quarter_kelly_clamped():
    # strong edge still clamps to <= 0.05
    k = quarter_kelly(0.7, 2.8)
    assert 0.0 <= k <= 0.05


def test_plus_ev_gate_blocks_low_confidence():
    assert is_plus_ev(7.8, "high", False, 3.0) is True
    assert is_plus_ev(7.8, "low", False, 3.0) is False
    assert is_plus_ev(7.8, "high", True, 3.0) is False   # stale
    assert is_plus_ev(1.0, "high", False, 3.0) is False  # below threshold
