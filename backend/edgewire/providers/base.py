"""Provider-agnostic adapter interface for odds sources.

EdgeWire's data strategy (per the ratified plan): start lean on The Odds API to
validate demand, but keep the rest of the system ignorant of *which* provider is
behind the data. Any provider (The Odds API now; OddsJam / SportsDataIO later)
implements `OddsProvider` and emits the SAME normalized records, so swapping the
feed is a config/adapter change — never a math or schema rewrite.

The normalized record types below are the contract between providers and the
ingestion layer. Provider adapters are responsible for translating their native
payloads into these dataclasses; nothing downstream sees provider-native JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass(frozen=True)
class NormalizedOutcome:
    """A single price for a single selection within a market at one book."""
    selection: str                 # team name, "Over"/"Under", or player+side
    price_american: int            # canonical price storage
    point: float | None = None     # spread/total line; None for moneyline
    description: str | None = None  # player name for props, else None


@dataclass(frozen=True)
class NormalizedMarket:
    market_key: str                # 'h2h','spreads','totals','player_pass_tds'...
    outcomes: list[NormalizedOutcome]
    book_last_update: str | None = None  # provider's last_update (ISO8601)


@dataclass(frozen=True)
class NormalizedBook:
    book_key: str                  # 'draftkings','fanduel','pinnacle',...
    title: str
    markets: list[NormalizedMarket]
    region: str | None = None


@dataclass(frozen=True)
class NormalizedEvent:
    provider: str                  # e.g. 'the_odds_api'
    provider_event_id: str
    sport_key: str                 # normalized, e.g. 'baseball_mlb'
    sport_title: str
    commence_time: str             # ISO8601 UTC
    home_team: str
    away_team: str
    books: list[NormalizedBook] = field(default_factory=list)


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a provider fetch, including quota metadata for auditing."""
    events: list[NormalizedEvent]
    requests_used: int | None = None
    requests_remaining: int | None = None
    raw_snapshot_timestamp: str | None = None  # historical-odds snapshot ts


class OddsProvider(Protocol):
    """Every odds source implements this. Keep it intentionally small."""

    #: Stable provider identifier stored on each event row.
    name: str

    def fetch_odds(
        self,
        sport_key: str,
        markets: Iterable[str],
        regions: Iterable[str],
    ) -> FetchResult:
        """Fetch current odds for a sport and return normalized events."""
        ...
