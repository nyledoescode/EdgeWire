"""EdgeWire intelligence engine — no-vig fair value, multi-book consensus, EV.

Implements Methodology Spec 01 (no-vig fair value & EV detection):
  - §1  odds conversion (delegates to edgewire.odds_math for the mechanics)
  - §2  de-vig: multiplicative (default) + additive (guarded); shin stub
  - §3  multi-book weighted consensus: staleness filter, robust-z outlier
        filter, weighted average, renormalize
  - §4  EV per offered price, leave-one-out consensus, +EV gates, quarter-Kelly

This is the "separate module built against Spec 01" that odds_math.py defers to.
Everything is computed in decimal-odds / probability space; American is display.

Design: pure functions over plain inputs (lists of BookQuote) so the quant's
reference vectors map directly onto unit tests. No DB or IO here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .odds_math import (
    american_to_decimal,
    american_to_implied_prob,
    decimal_to_american,
)

# --- Spec 01 §3.2 book weights (config-driven; tunable vs CLV later) ----------
SHARP_TIER = {"pinnacle", "circasports", "betonlineag"}
MAJOR_TIER = {"draftkings", "fanduel", "betmgm", "caesars"}

WEIGHT_SHARP = 3.0
WEIGHT_MAJOR = 1.5
WEIGHT_OTHER = 1.0


def book_weight(book_key: str) -> float:
    if book_key in SHARP_TIER:
        return WEIGHT_SHARP
    if book_key in MAJOR_TIER:
        return WEIGHT_MAJOR
    return WEIGHT_OTHER


# --- Spec 01 §3.3 staleness thresholds (seconds) ------------------------------
STALENESS_TAU = {
    "live": 15,
    "pregame_major": 120,
    "pregame_props": 300,
    "futures": 1800,
}

# --- Spec 01 §4.3 +EV thresholds (EV%, by market class) -----------------------
EV_THRESHOLD = {
    "mainline": 2.0,
    "soccer_or_major_props": 3.0,
    "props_minor": 4.0,
    "futures": 5.0,
}

ROBUST_Z_CUTOFF = 3.5        # §3.4
MAD_SCALE = 0.6745           # §3.4 (makes MAD comparable to σ)
KELLY_FRACTION = 0.25        # §4.6 quarter Kelly
KELLY_CAP = 0.05             # §4.6 never suggest > 5% bankroll


# =============================================================================
# §1 conversions (thin wrappers so callers import one module)
# =============================================================================
def implied_prob(american: int) -> float:
    """Raw (vig-inclusive) implied probability from American odds (§1.2)."""
    return american_to_implied_prob(american)


def prob_to_american(p: float) -> int:
    """Fair probability -> American odds for display (§1.3)."""
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be in (0,1)")
    return decimal_to_american(1.0 / p)


# =============================================================================
# §2 de-vig
# =============================================================================
def devig(probs: list[float], method: str = "multiplicative") -> list[float]:
    """Remove vig from a complete set of raw implied probabilities.

    `probs` must be the raw q_i for ALL mutually-exclusive outcomes of one
    market at one book (they sum to > 1). Returns fair p_i summing to 1.
    """
    if not probs:
        raise ValueError("empty probs")
    M = sum(probs)
    if M <= 0:
        raise ValueError("probabilities must be positive")

    if method == "multiplicative":
        # §2.1 p_i = q_i / M
        return [q / M for q in probs]

    if method == "additive":
        # §2.2 p_i = q_i - H/n ; guard against <=0 -> fall back to multiplicative
        n = len(probs)
        H = M - 1.0
        fair = [q - H / n for q in probs]
        if any(p <= 0 for p in fair):
            return [q / M for q in probs]
        # additive may not sum to exactly 1 due to the equal-margin assumption;
        # renormalize to be safe (still differs from multiplicative in shape).
        s = sum(fair)
        return [p / s for p in fair]

    if method == "shin":
        # §2.3 deferred to v2 — stub raises so callers can't silently get wrong math.
        raise NotImplementedError("Shin de-vig deferred to v2 (Spec 01 §2.3)")

    raise ValueError(f"unknown devig method: {method}")


def devig_american(americans: list[int], method: str = "multiplicative") -> list[float]:
    """Convenience: de-vig directly from a list of American prices for a market."""
    return devig([implied_prob(a) for a in americans], method=method)


# =============================================================================
# §3 multi-book consensus
# =============================================================================
@dataclass
class BookQuote:
    """One book's price for a single outcome, with its sibling(s) for de-vig.

    `market_american` is the full list of American prices for ALL outcomes of
    this market at this book (needed to de-vig within the book). `outcome_index`
    is which entry in that list this quote refers to.
    """
    book_key: str
    market_american: list[int]
    outcome_index: int
    age_seconds: float | None = None       # now - book_last_update
    is_sharp: bool = False

    def no_vig_prob(self, method: str = "multiplicative") -> float:
        """This book's own de-vigged probability for the outcome (§2)."""
        return devig_american(self.market_american, method=method)[self.outcome_index]


@dataclass
class ConsensusResult:
    fair_prob: float
    fair_american: int
    n_books: int
    confidence: str                         # high|medium|low
    excluded_books: list[str] = field(default_factory=list)
    per_book: dict[str, float] = field(default_factory=dict)   # book -> no_vig_prob


def _confidence(n: int) -> str:
    if n >= 5:
        return "high"
    if n >= 3:
        return "medium"
    return "low"


def _staleness_filter(quotes: list[BookQuote], tau: float | None) -> list[BookQuote]:
    if tau is None:
        return list(quotes)
    out = []
    for q in quotes:
        if q.age_seconds is not None and q.age_seconds > tau:
            continue
        out.append(q)
    return out


def _outlier_filter(
    pairs: list[tuple[str, float]]
) -> tuple[list[tuple[str, float]], list[str]]:
    """Robust-z (MAD) outlier removal (§3.4).

    pairs: list of (book_key, no_vig_prob). Returns (kept, excluded_book_keys).
    Guard: if <3 books or MAD==0, keep all.
    """
    if len(pairs) < 3:
        return pairs, []
    vals = [p for _, p in pairs]
    med = median(vals)
    mad = median([abs(v - med) for v in vals])
    if mad == 0:
        return pairs, []
    kept, excluded = [], []
    for book, v in pairs:
        z = MAD_SCALE * (v - med) / mad
        if abs(z) > ROBUST_Z_CUTOFF:
            excluded.append(book)
        else:
            kept.append((book, v))
    return kept, excluded


def consensus(
    quotes: list[BookQuote],
    method: str = "multiplicative",
    tau: float | None = None,
    weights: dict[str, float] | None = None,
) -> ConsensusResult:
    """Weighted multi-book consensus fair probability for ONE outcome (§3).

    Pipeline: de-vig within each book -> staleness filter -> robust-z outlier
    filter -> weighted average -> (caller renormalizes across outcomes).
    """
    fresh = _staleness_filter(quotes, tau)
    pairs = [(q.book_key, q.no_vig_prob(method)) for q in fresh]
    per_book = dict(pairs)

    kept, excluded = _outlier_filter(pairs)
    if not kept:
        kept = pairs  # never end up with nothing

    def w(book: str) -> float:
        if weights and book in weights:
            return weights[book]
        return book_weight(book)

    num = sum(w(b) * p for b, p in kept)
    den = sum(w(b) for b, _ in kept)
    fair = num / den if den else median([p for _, p in kept])

    return ConsensusResult(
        fair_prob=fair,
        fair_american=prob_to_american(fair),
        n_books=len(kept),
        confidence=_confidence(len(kept)),
        excluded_books=excluded,
        per_book=per_book,
    )


def renormalize(consensuses: list[ConsensusResult]) -> list[float]:
    """Renormalize a market's per-outcome consensus probs to sum to 1 (§3.1.4)."""
    total = sum(c.fair_prob for c in consensuses)
    if total <= 0:
        raise ValueError("consensus probabilities sum to <= 0")
    return [c.fair_prob / total for c in consensuses]


def leave_one_out_prob(
    quotes: list[BookQuote],
    book_key: str,
    method: str = "multiplicative",
    tau: float | None = None,
    weights: dict[str, float] | None = None,
) -> ConsensusResult:
    """Consensus EXCLUDING `book_key` — the fair reference when grading that
    book's own price for +EV (§4.5). Prevents a soft book from masking its own
    edge."""
    others = [q for q in quotes if q.book_key != book_key]
    return consensus(others, method=method, tau=tau, weights=weights)


# =============================================================================
# §4 expected value
# =============================================================================
def ev_pct(fair_prob: float, offered_decimal: float) -> float:
    """EV% on stake against a fair probability (§4.1): (p·d − 1)·100."""
    return (fair_prob * offered_decimal - 1.0) * 100.0


def ev_pct_american(fair_prob: float, offered_american: int) -> float:
    return ev_pct(fair_prob, american_to_decimal(offered_american))


def prob_edge(fair_prob: float, offered_decimal: float) -> float:
    """p̄ − q_offer (§4.2): edge vs the book's implied (with-vig) price."""
    return fair_prob - (1.0 / offered_decimal)


def quarter_kelly(fair_prob: float, offered_decimal: float) -> float:
    """Fractional (quarter) Kelly stake hint, clamped to [0, KELLY_CAP] (§4.6)."""
    b = offered_decimal - 1.0
    if b <= 0:
        return 0.0
    f_star = (fair_prob * offered_decimal - 1.0) / b
    rec = KELLY_FRACTION * f_star
    return max(0.0, min(rec, KELLY_CAP))


def is_plus_ev(
    ev_percent: float,
    confidence: str,
    stale: bool,
    threshold: float,
) -> bool:
    """+EV gate (§4.3): EV ≥ θ AND confidence ≥ medium AND not stale."""
    if stale:
        return False
    if confidence == "low":
        return False
    return ev_percent >= threshold
