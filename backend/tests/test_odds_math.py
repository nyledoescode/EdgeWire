"""Sanity tests for odds-format conversions (mechanical only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.odds_math import (
    american_to_decimal,
    decimal_to_american,
    american_to_implied_prob,
)


def test_american_to_decimal_favorite():
    assert american_to_decimal(-110) == pytest.approx(1.909, abs=1e-3)


def test_american_to_decimal_underdog():
    assert american_to_decimal(150) == pytest.approx(2.50, abs=1e-9)


def test_roundtrip_underdog():
    assert decimal_to_american(american_to_decimal(145)) == 145


def test_roundtrip_favorite():
    assert decimal_to_american(american_to_decimal(-135)) == -135


def test_implied_prob_even():
    # +100 / -100 both imply 50%
    assert american_to_implied_prob(100) == pytest.approx(0.5)
    assert american_to_implied_prob(-100) == pytest.approx(0.5)


def test_implied_prob_two_sided_sum_exceeds_one():
    # Vig-inclusive probabilities of a paired market sum to > 1 (the hold).
    p_over = american_to_implied_prob(-110)
    p_under = american_to_implied_prob(-110)
    assert p_over + p_under > 1.0


def test_zero_rejected():
    with pytest.raises(ValueError):
        american_to_decimal(0)
