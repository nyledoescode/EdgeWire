"""Live-mode ingest adapter tests — ZERO quota.

These NEVER hit the live API. A FakeProvider replays a captured The Odds API v4
response so we exercise the exact _parse_events -> ingest_fetch_result path and
the refresh_live()/data_source_status() orchestration without spending credits.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from edgewire.db.database import connect, init_db
from edgewire.providers.base import FetchResult
from edgewire.providers.the_odds_api import _parse_events
from edgewire.ingest import live

CAPTURE = Path(__file__).resolve().parent / "fixtures" / "the_odds_api_live_capture.json"


class FakeProvider:
    """Drop-in OddsProvider that replays a captured payload + quota headers."""
    name = "the_odds_api"

    def __init__(self, payload=None, used=1, remaining=499, raise_exc=None):
        self._payload = payload if payload is not None else json.loads(CAPTURE.read_text())
        self._used, self._remaining, self._raise = used, remaining, raise_exc
        self.calls = []

    def fetch_odds(self, sport_key, markets=("h2h",), regions=("us",)):
        self.calls.append((sport_key, tuple(markets), tuple(regions)))
        if self._raise:
            raise self._raise
        return FetchResult(
            events=_parse_events(self._payload),
            requests_used=self._used,
            requests_remaining=self._remaining,
        )


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    init_db(c)
    return c


def test_live_available_reflects_env(monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    assert live.live_mode_available() is False
    monkeypatch.setenv("THE_ODDS_API_KEY", "abc123")
    assert live.live_mode_available() is True


def test_refresh_live_maps_into_same_schema(conn):
    prov = FakeProvider(used=1, remaining=499)
    res = live.refresh_live(conn, provider=prov, logger=lambda *_: None)
    assert res.ok and res.mode == "live"
    assert res.requests_remaining == 499 and res.requests_used == 1
    assert res.events_seen == 1 and res.snapshots_written > 0
    # Quota-frugal defaults were used.
    assert prov.calls == [("baseball_mlb", ("h2h",), ("us",))]
    # Real captured game landed in the normalized store (NOT the Red Sox fixture).
    row = conn.execute(
        "SELECT home_team, away_team FROM event WHERE provider_event_id = 'capture_evt_1'"
    ).fetchone()
    assert row["home_team"] == "Chicago Cubs"
    # Quota persisted on the ingest_run row for auditing.
    q = conn.execute(
        "SELECT requests_remaining FROM ingest_run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert q["requests_remaining"] == 499


def test_key_absent_no_network(conn, monkeypatch):
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    res = live.refresh_live(conn)  # no provider injected -> must refuse
    assert res.ok is False and res.mode == "fixture"
    assert "not set" in res.error


def test_fetch_failure_degrades_gracefully(conn):
    prov = FakeProvider(raise_exc=RuntimeError("HTTP 429 quota exceeded"))
    res = live.refresh_live(conn, provider=prov, logger=lambda *_: None)
    assert res.ok is False and res.mode == "live"
    assert "429" in res.error
    # No odds fabricated; a failed run was recorded for auditing.
    assert conn.execute("SELECT COUNT(*) c FROM odds_snapshot").fetchone()["c"] == 0
    err = conn.execute(
        "SELECT status FROM ingest_run ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert err["status"] == "error"


def test_empty_response_not_an_error(conn):
    prov = FakeProvider(payload=[], used=1, remaining=498)
    res = live.refresh_live(conn, provider=prov, logger=lambda *_: None)
    assert res.ok is True and res.events_seen == 0
    assert res.requests_remaining == 498


def test_status_fixture_mode_when_no_live_run(conn):
    from edgewire.ingest.pipeline import ingest_fetch_result
    payload = json.loads((Path(__file__).resolve().parents[1] /
                          "data" / "fixtures" / "the_odds_api_baseball_mlb.json").read_text())
    ingest_fetch_result(conn, FetchResult(events=_parse_events(payload)),
                        "the_odds_api", "baseball_mlb")
    st = live.data_source_status(conn)
    assert st.mode == "fixture"          # no live run with quota headers yet
    assert st.quota_remaining is None
    assert st.last_ingest_at is not None


def test_status_live_mode_and_quota(conn):
    prov = FakeProvider(used=3, remaining=497)
    live.refresh_live(conn, provider=prov, logger=lambda *_: None)
    st = live.data_source_status(conn)
    assert st.mode == "live"
    assert st.quota_remaining == 497
    assert st.degraded is False


def test_status_quota_exhausted_degraded(conn):
    prov = FakeProvider(used=500, remaining=0)
    live.refresh_live(conn, provider=prov, logger=lambda *_: None)
    st = live.data_source_status(conn)
    assert st.degraded is True
    assert "quota exhausted" in st.degraded_reason
