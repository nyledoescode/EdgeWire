"""Tests for the read-side API contract (edgewire/api.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.db.database import connect, init_db
from edgewire.ingest.pipeline import ingest_fetch_result
from edgewire.providers.base import FetchResult
from edgewire.providers.the_odds_api import _parse_events
from edgewire import api

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def _load(name: str) -> FetchResult:
    return FetchResult(events=_parse_events(json.loads((FIXTURE_DIR / name).read_text())))


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    init_db(c)
    ingest_fetch_result(c, _load("the_odds_api_baseball_mlb.json"), "the_odds_api", "baseball_mlb")
    ingest_fetch_result(c, _load("the_odds_api_baseball_mlb_t2.json"), "the_odds_api", "baseball_mlb")
    return c


def test_list_events(conn):
    events = api.list_events(conn, "baseball_mlb")
    assert len(events) == 2
    assert {e["home_team"] for e in events} == {"New York Yankees", "Los Angeles Dodgers"}


def test_line_shop_sorted_best_first(conn):
    eid = api.list_events(conn, "baseball_mlb")[0]["id"]
    rows = api.line_shop(conn, eid, "h2h")
    # Yankees selection rows should be sorted best (highest American) first.
    yanks = [r for r in rows if r["selection"] == "New York Yankees"]
    prices = [r["price_american"] for r in yanks]
    assert prices == sorted(prices, reverse=True)


def test_movement_history(conn):
    eid = api.list_events(conn, "baseball_mlb")[0]["id"]
    hist = api.movement(conn, eid, "h2h", "pinnacle", "New York Yankees")
    assert [h["price_american"] for h in hist] == [-148, -162]
    assert hist[0]["is_opening"] == 1
