"""Pure odds-format conversions.

IMPORTANT: This module contains ONLY mechanical conversions between odds
formats. It deliberately does NOT implement no-vig fair value, EV detection,
or any probability/edge math — that lives in a separate module built strictly
against the quant's approved Spec 01 (pending in /methodology). Keeping the
mechanical conversions separate means the EV layer can be reviewed in isolation.
"""
from __future__ import annotations


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds.

    +150 -> 2.50,  -110 -> 1.909...
    """
    a = int(american)
    if a == 0:
        raise ValueError("American odds cannot be 0")
    if a > 0:
        return 1.0 + a / 100.0
    return 1.0 + 100.0 / abs(a)


def decimal_to_american(decimal: float) -> int:
    """Convert decimal odds to American odds (rounded to nearest integer)."""
    d = float(decimal)
    if d <= 1.0:
        raise ValueError("Decimal odds must be > 1.0")
    if d >= 2.0:
        return round((d - 1.0) * 100.0)
    return round(-100.0 / (d - 1.0))


def american_to_implied_prob(american: int) -> float:
    """Raw (vig-inclusive) implied probability from American odds.

    NOTE: This is the naive implied probability that still contains the
    bookmaker's margin. De-vigging to a fair probability is a quant-spec
    operation and is intentionally not done here.
    """
    a = int(american)
    if a == 0:
        raise ValueError("American odds cannot be 0")
    if a > 0:
        return 100.0 / (a + 100.0)
    return abs(a) / (abs(a) + 100.0)
