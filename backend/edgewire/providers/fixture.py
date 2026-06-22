"""Fixture provider — replays a saved The Odds API v4 payload from disk.

Lets the whole pipeline run end-to-end with NO API key and NO network, so we
can develop and test ingestion/CLV before the owner provisions THE_ODDS_API_KEY.
It reuses the live adapter's `_parse_events` so the fixture exercises the exact
same normalization code path as production.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .base import FetchResult
from .the_odds_api import _parse_events

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"


class FixtureTheOddsAPIProvider:
    """Drop-in OddsProvider backed by a JSON fixture file per sport."""

    name = "the_odds_api"

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self.fixture_dir = fixture_dir or _FIXTURE_DIR

    def _fixture_path(self, sport_key: str) -> Path:
        return self.fixture_dir / f"the_odds_api_{sport_key}.json"

    def fetch_odds(
        self,
        sport_key: str,
        markets: Iterable[str] = ("h2h", "spreads", "totals"),
        regions: Iterable[str] = ("us",),
    ) -> FetchResult:
        path = self._fixture_path(sport_key)
        if not path.exists():
            raise FileNotFoundError(f"No fixture for sport '{sport_key}': {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return FetchResult(
            events=_parse_events(payload),
            requests_used=None,
            requests_remaining=None,
        )
