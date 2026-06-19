"""Vector-driven conformance tests: load the quant's canonical test-vectors.json
verbatim and assert the engine matches. This file is the single source of truth
for numerical correctness — if the quant updates vectors, drop in the new JSON.

Source: /home/team/shared/methodology/test-vectors.json (copied alongside here).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.odds_math import american_to_decimal, american_to_implied_prob, decimal_to_american
from edgewire.intelligence import (
    BookQuote,
    consensus,
    devig_american,
    ev_pct,
    leave_one_out_prob,
    quarter_kelly,
    prob_to_american,
)
from edgewire.clv import grade_clv, wilson_ci

VECTORS = json.loads((Path(__file__).resolve().parent / "quant_test_vectors.json").read_text())


@pytest.mark.parametrize("v", VECTORS["odds_conversion"])
def test_odds_conversion(v):
    assert american_to_decimal(v["american"]) == pytest.approx(v["decimal"], abs=1e-4)
    assert american_to_implied_prob(v["american"]) == pytest.approx(v["implied_prob"], abs=1e-4)


@pytest.mark.parametrize("v", VECTORS["decimal_to_american"])
def test_decimal_to_american(v):
    assert decimal_to_american(v["decimal"]) == v["american"]


def test_devig_2way_balanced():
    assert devig_american([-110, -110]) == pytest.approx(VECTORS["devig_2way_-110_-110"]["fair"], abs=1e-5)


def test_devig_2way_ml():
    assert devig_american([-200, 170]) == pytest.approx(VECTORS["devig_2way_-200_+170"]["fair"], abs=1e-5)


def test_devig_3way():
    assert devig_american([150, 220, 180]) == pytest.approx(VECTORS["devig_3way_+150_+220_+180"]["fair"], abs=1e-4)


def test_devig_additive():
    assert devig_american([-200, 170], method="additive") == pytest.approx(
        VECTORS["devig_additive_-200_+170"]["fair"], abs=1e-4
    )


def _vigfree_pair(p_home):
    return [decimal_to_american(1.0 / p_home), decimal_to_american(1.0 / (1.0 - p_home))]


def test_consensus_nba_home():
    exp = VECTORS["consensus_nba_home"]
    quotes = [
        BookQuote("pinnacle", _vigfree_pair(0.611), 0, is_sharp=True),
        BookQuote("draftkings", _vigfree_pair(0.620), 0),
        BookQuote("fanduel", _vigfree_pair(0.618), 0),
        BookQuote("softx", _vigfree_pair(0.660), 0),
    ]
    res = consensus(quotes)
    assert res.excluded_books == exp["excluded"]
    assert res.fair_prob == pytest.approx(exp["consensus_fair_prob"], abs=1e-3)


def test_leave_one_out_ev():
    exp = VECTORS["leave_one_out_ev"]
    bw = exp["books_home_fairprob_weight"]
    quotes = [BookQuote(b, _vigfree_pair(p), 0) for b, (p, _w) in bw.items()]
    weights = {b: w for b, (_p, w) in bw.items()}
    loo = leave_one_out_prob(quotes, "fanduel", weights=weights)
    assert loo.fair_prob == pytest.approx(exp["loo_exclude_fanduel"], abs=2e-3)
    ev = ev_pct(loo.fair_prob, exp["grade_fanduel_home_offer_decimal"])
    assert ev == pytest.approx(exp["ev_vs_loo_pct"], abs=0.2)


@pytest.mark.parametrize("v", VECTORS["ev_examples"])
def test_ev_examples(v):
    assert ev_pct(v["fair_prob"], v["offer_decimal"]) == pytest.approx(v["ev_pct"], abs=0.05)


def test_kelly_quarter():
    assert quarter_kelly(0.385, 2.8) == pytest.approx(VECTORS["kelly_quarter_p0.385_+180"], abs=1e-4)


def test_clv_example():
    e = VECTORS["clv_example"]
    g = grade_clv(e["d_bet"], e["p_bet"], e["p_close"])
    assert g.clv_prob == pytest.approx(e["clv_prob"], abs=1e-5)
    assert bool(g.beat_close) == e["beat_close"]
    assert g.clv_pct == pytest.approx(e["clv_pct"], abs=0.02)
    assert g.clv_cents == pytest.approx(e["clv_cents"], abs=1)


@pytest.mark.parametrize("v", VECTORS["wilson_ci"])
def test_wilson(v):
    lo, hi = wilson_ci(v["k"], v["n"])
    assert lo == pytest.approx(v["ci95"][0], abs=2e-3)
    assert hi == pytest.approx(v["ci95"][1], abs=2e-3)
