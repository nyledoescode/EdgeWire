"""The Odds API (v4) provider adapter.

Written against the documented v4 schema:
  GET https://api.the-odds-api.com/v4/sports/{sport}/odds
      ?apiKey=...&regions=us&markets=h2h,spreads,totals&oddsFormat=american

Response shape (per https://the-odds-api.com/liveapi/guides/v4/):
  [
    {
      "id": "<event id>",
      "sport_key": "baseball_mlb",
      "sport_title": "MLB",
      "commence_time": "2026-06-15T23:10:00Z",
      "home_team": "...",
      "away_team": "...",
      "bookmakers": [
        {
          "key": "draftkings", "title": "DraftKings",
          "last_update": "2026-06-15T22:01:00Z",
          "markets": [
            {
              "key": "h2h", "last_update": "...",
              "outcomes": [ {"name": "...", "price": -135}, ... ]
            },
            {
              "key": "spreads", ...,
              "outcomes": [ {"name":"...","price":-110,"point":-1.5}, ... ]
            }
          ]
        }
      ]
    }
  ]

Quota headers returned by the API:
  x-requests-used, x-requests-remaining.

KEY/SECRET NEEDED FROM OWNER (do not hardcode): THE_ODDS_API_KEY.
Until provisioned, use FixtureTheOddsAPIProvider (fixtures/) — this class will
make a real HTTP call only when given a key, and is unit-tested via _parse().
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Iterable

from .base import (
    FetchResult,
    NormalizedBook,
    NormalizedEvent,
    NormalizedMarket,
    NormalizedOutcome,
    OddsProvider,
)

_BASE_URL = "https://api.the-odds-api.com/v4"

# Sharp books used downstream as fair-value anchors (Spec 01 §3.2 weights).
SHARP_BOOKS = {"pinnacle", "circasports", "betonlineag"}

# Spec 01 §3.2 flag: Pinnacle is NOT in The Odds API us/us2 feeds — it is only
# available under the `eu` region key (and not for all sports). Request `eu` to
# capture the sharpest anchor where possible.
SHARP_BOOK_REGION = {"pinnacle": "eu", "betonlineag": "eu", "circasports": "us"}


def _validate_american(price: int) -> int:
    """Spec 01 §1.5/§8: reject malformed quotes with |A| < 100."""
    a = int(price)
    if abs(a) < 100:
        raise ValueError(f"Malformed American odds (|A|<100): {a}")
    return a


def _parse_events(payload: list[dict[str, Any]]) -> list[NormalizedEvent]:
    """Translate raw v4 JSON into normalized events. Pure function -> testable."""
    events: list[NormalizedEvent] = []
    for ev in payload:
        books: list[NormalizedBook] = []
        for bk in ev.get("bookmakers", []):
            markets: list[NormalizedMarket] = []
            for mk in bk.get("markets", []):
                outcomes = [
                    NormalizedOutcome(
                        selection=oc["name"],
                        price_american=_validate_american(oc["price"]),
                        point=(float(oc["point"]) if oc.get("point") is not None else None),
                        description=oc.get("description"),
                    )
                    for oc in mk.get("outcomes", [])
                ]
                markets.append(
                    NormalizedMarket(
                        market_key=mk["key"],
                        outcomes=outcomes,
                        book_last_update=mk.get("last_update") or bk.get("last_update"),
                    )
                )
            books.append(
                NormalizedBook(
                    book_key=bk["key"],
                    title=bk.get("title", bk["key"]),
                    markets=markets,
                )
            )
        events.append(
            NormalizedEvent(
                provider="the_odds_api",
                provider_event_id=ev["id"],
                sport_key=ev["sport_key"],
                sport_title=ev.get("sport_title", ev["sport_key"]),
                commence_time=ev["commence_time"],
                home_team=ev["home_team"],
                away_team=ev["away_team"],
                books=books,
            )
        )
    return events


class TheOddsAPIProvider(OddsProvider):
    """Live adapter. Requires THE_ODDS_API_KEY. Makes real HTTP requests."""

    name = "the_odds_api"

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        self.api_key = api_key or os.environ.get("THE_ODDS_API_KEY")
        self.timeout = timeout

    def fetch_odds(
        self,
        sport_key: str,
        markets: Iterable[str] = ("h2h", "spreads", "totals"),
        regions: Iterable[str] = ("us",),
    ) -> FetchResult:
        if not self.api_key:
            raise RuntimeError(
                "THE_ODDS_API_KEY not set. Provision the key or use the fixture "
                "provider for local development."
            )
        params = {
            "apiKey": self.api_key,
            "regions": ",".join(regions),
            "markets": ",".join(markets),
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        url = f"{_BASE_URL}/sports/{sport_key}/odds?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
            used = resp.headers.get("x-requests-used")
            remaining = resp.headers.get("x-requests-remaining")
        return FetchResult(
            events=_parse_events(raw),
            requests_used=int(used) if used is not None else None,
            requests_remaining=int(remaining) if remaining is not None else None,
        )
