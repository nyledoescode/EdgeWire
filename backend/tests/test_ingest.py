"""End-to-end ingestion tests against fixtures (no network, no API key)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.db.database import connect, init_db
from edgewire.ingest.pipeline import ingest_fetch_result
from edgewire.providers.fixture import FixtureTheOddsAPIProvider
from edgewire.providers.base import FetchResult
from edgewire.providers.the_odds_api import _parse_events

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures"


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "test.db"
    c = connect(db)
    init_db(c)
    return c


def _load(name: str) -> FetchResult:
    payload = json.loads((FIXTURE_DIR / name).read_text())
    return FetchResult(events=_parse_events(payload))


def test_fixture_provider_parses(conn):
    provider = FixtureTheOddsAPIProvider()
    result = provider.fetch_odds("baseball_mlb")
    assert len(result.events) == 2
    yanks = result.events[0]
    assert yanks.home_team == "New York Yankees"
    assert any(b.book_key == "pinnacle" for b in yanks.books)


def test_first_ingest_flags_openings(conn):
    result = _load("the_odds_api_baseball_mlb.json")
    summary = ingest_fetch_result(conn, result, "the_odds_api", "baseball_mlb")
    assert summary["events_seen"] == 2
    assert summary["snapshots_written"] > 0
    # Every snapshot from the first run is an opening observation.
    total = conn.execute("SELECT COUNT(*) c FROM odds_snapshot").fetchone()["c"]
    openings = conn.execute(
        "SELECT COUNT(*) c FROM odds_snapshot WHERE is_opening = 1"
    ).fetchone()["c"]
    assert openings == total


def test_dedup_skips_unchanged(conn):
    result = _load("the_odds_api_baseball_mlb.json")
    ingest_fetch_result(conn, result, "the_odds_api", "baseball_mlb")
    before = conn.execute("SELECT COUNT(*) c FROM odds_snapshot").fetchone()["c"]
    # Re-ingest identical data — nothing should be written.
    again = _load("the_odds_api_baseball_mlb.json")
    summary2 = ingest_fetch_result(conn, again, "the_odds_api", "baseball_mlb")
    after = conn.execute("SELECT COUNT(*) c FROM odds_snapshot").fetchone()["c"]
    assert summary2["snapshots_written"] == 0
    assert before == after


def test_movement_creates_new_rows_not_openings(conn):
    ingest_fetch_result(conn, _load("the_odds_api_baseball_mlb.json"),
                        "the_odds_api", "baseball_mlb")
    # Second snapshot moves Yankees ML and the total.
    ingest_fetch_result(conn, _load("the_odds_api_baseball_mlb_t2.json"),
                        "the_odds_api", "baseball_mlb")

    # The Yankees moneyline at Pinnacle should now have 2 observations,
    # exactly one of which is the opening.
    rows = conn.execute(
        """SELECT s.price_american, s.is_opening
           FROM odds_snapshot s
           JOIN event e ON e.id = s.event_id
           JOIN bookmaker b ON b.id = s.bookmaker_id
           JOIN market_type m ON m.id = s.market_type_id
           WHERE e.home_team = 'New York Yankees'
             AND b.book_key = 'pinnacle'
             AND m.market_key = 'h2h'
             AND s.selection = 'New York Yankees'
           ORDER BY s.observed_at""",
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["is_opening"] == 1
    assert rows[1]["is_opening"] == 0
    assert rows[0]["price_american"] == -148   # opening
    assert rows[1]["price_american"] == -162   # moved


def test_latest_odds_view(conn):
    ingest_fetch_result(conn, _load("the_odds_api_baseball_mlb.json"),
                        "the_odds_api", "baseball_mlb")
    ingest_fetch_result(conn, _load("the_odds_api_baseball_mlb_t2.json"),
                        "the_odds_api", "baseball_mlb")
    # v_latest_odds should return the moved (-162) price, not the opening.
    row = conn.execute(
        """SELECT v.price_american
           FROM v_latest_odds v
           JOIN event e ON e.id = v.event_id
           JOIN bookmaker b ON b.id = v.bookmaker_id
           JOIN market_type m ON m.id = v.market_type_id
           WHERE e.home_team = 'New York Yankees'
             AND b.book_key = 'pinnacle'
             AND m.market_key = 'h2h'
             AND v.selection = 'New York Yankees'""",
    ).fetchone()
    assert row["price_american"] == -162


def test_sharp_book_flagged(conn):
    ingest_fetch_result(conn, _load("the_odds_api_baseball_mlb.json"),
                        "the_odds_api", "baseball_mlb")
    row = conn.execute(
        "SELECT is_sharp FROM bookmaker WHERE book_key = 'pinnacle'"
    ).fetchone()
    assert row["is_sharp"] == 1


def test_pinnacle_region_is_eu(conn):
    # Spec 01 §3.2: Pinnacle is captured via the EU region, not US.
    ingest_fetch_result(conn, _load("the_odds_api_baseball_mlb.json"),
                        "the_odds_api", "baseball_mlb")
    row = conn.execute(
        "SELECT region FROM bookmaker WHERE book_key = 'pinnacle'"
    ).fetchone()
    assert row["region"] == "eu"


def test_malformed_odds_rejected():
    # Spec 01 §1.5/§8: quotes with |A| < 100 are malformed and must be rejected.
    from edgewire.providers.the_odds_api import _validate_american
    with pytest.raises(ValueError):
        _validate_american(50)
    assert _validate_american(-110) == -110
    assert _validate_american(100) == 100


def test_spec_tables_exist(conn):
    # Spec 02 §4.2 (bet_signal) and Spec 03 §5.2 (movement_*) tables present.
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"movement_point", "movement_signal", "bet_signal"} <= names


def test_snapshot_has_suspended_column(conn):
    # Spec 02 §4.1 requires is_suspended for closing-snapshot exclusion.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(odds_snapshot)").fetchall()}
    assert "is_suspended" in cols
