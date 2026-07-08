"""Tests for screen assemblers + CLV grading job (fixture-backed, no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.db.database import connect, init_db
from edgewire.ingest.pipeline import ingest_fetch_result
from edgewire.providers.base import FetchResult
from edgewire.providers.the_odds_api import _parse_events
from edgewire import screens, clv_grading
from edgewire.odds_math import american_to_decimal

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def _load(name):
    return FetchResult(events=_parse_events(json.loads((FIXTURE_DIR / name).read_text())))


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    init_db(c)
    ingest_fetch_result(c, _load("the_odds_api_baseball_mlb.json"), "the_odds_api", "baseball_mlb")
    ingest_fetch_result(c, _load("the_odds_api_baseball_mlb_t2.json"), "the_odds_api", "baseball_mlb")
    return c


# ---- EV screen ---------------------------------------------------------------
def test_ev_screen_shape(conn):
    data = screens.build_ev_screen(conn, sport_key="baseball_mlb")
    assert "generatedAt" in data and isinstance(data["events"], list)
    assert len(data["events"]) == 2
    ev = data["events"][0]
    assert {"id", "sport", "startTime", "homeTeam", "awayTeam", "markets"} <= ev.keys()
    assert ev["sport"] == "MLB"


def test_ev_screen_outcome_has_fair_and_ev(conn):
    data = screens.build_ev_screen(conn, sport_key="baseball_mlb")
    h2h = next(m for m in data["events"][0]["markets"] if m["type"] == "h2h")
    oc = h2h["outcomes"][0]
    # server-computed fair value present and in (0,1)
    assert 0.0 < oc["fairProb"] < 1.0
    assert oc["fairPrice"] is not None
    # ev is a fraction; bestPrice/bestBook from line shopping
    assert isinstance(oc["ev"], float)
    assert oc["bestBook"] in {p["book"] for p in oc["prices"]}
    # best price really is the max among prices
    assert oc["bestPrice"] == max(p["price"] for p in oc["prices"])


def test_ev_screen_fair_probs_sum_to_one(conn):
    data = screens.build_ev_screen(conn, sport_key="baseball_mlb")
    h2h = next(m for m in data["events"][0]["markets"] if m["type"] == "h2h")
    total = sum(o["fairProb"] for o in h2h["outcomes"])
    assert total == pytest.approx(1.0, abs=1e-6)


def test_ev_screen_movement_present(conn):
    data = screens.build_ev_screen(conn, sport_key="baseball_mlb")
    h2h = next(m for m in data["events"][0]["markets"] if m["type"] == "h2h")
    # Yankees moved between t1 and t2 -> movement series has >= 2 points for some book
    any_multi = any(len(o["movement"]) >= 2 for o in h2h["outcomes"])
    assert any_multi


# ---- CLV grading -------------------------------------------------------------
def _log_bet(conn, event_id, market_key, outcome, american, fair_prob):
    conn.execute(
        """INSERT INTO bet_signal
            (bet_id, event_id, sport_key, market_key, outcome, logged_at_utc,
             bet_book, bet_decimal, bet_american, fair_prob_at_bet, clv_status)
           VALUES (?, ?, 'baseball_mlb', ?, ?, '2026-06-15T22:05:00Z',
                   'draftkings', ?, ?, ?, 'pending')""",
        (f"bet_{outcome}_{market_key}", event_id, market_key, outcome,
         american_to_decimal(american), american, fair_prob),
    )
    conn.commit()


def test_clv_grading_and_summary(conn):
    # Log a bet on the Yankees ML at the opening DK price (-135) with a fair
    # prob; after grading against the (moved) closing consensus, it should grade.
    eid = conn.execute(
        "SELECT id FROM event WHERE home_team='New York Yankees'"
    ).fetchone()["id"]
    _log_bet(conn, eid, "h2h", "New York Yankees", -135, fair_prob=0.57)

    graded = clv_grading.grade_all(conn)
    assert graded >= 1

    summary = screens.build_clv_summary(conn)
    assert summary["sampleSize"] >= 1
    # mandatory honesty fields present
    assert "beatRateCI95" in summary and len(summary["beatRateCI95"]) == 2
    assert "avgClvPctCI95" in summary
    assert summary["displayGate"] == "building"   # n<30
    assert len(summary["records"]) >= 1
    rec = summary["records"][0]
    assert {"takenPrice", "closingPrice", "clvPct"} <= rec.keys()
