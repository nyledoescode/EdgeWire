"""EdgeWire HTTP API — stdlib http.server (memory-light, no framework deps).

Endpoints (per /home/team/shared/edgewire-web/API_CONTRACT.md):
  GET /api/health                       -> {status, ...}
  GET /api/ev-screen?sport=MLB&market=h2h  -> EvScreenResponse
  GET /api/clv-summary?window=90d       -> ClvSummary
  GET /api/capabilities                 -> Spec 03 §5.3 capability flags

Serves fixture-backed data from the SQLite store so the frontend can wire
mock -> real immediately. Tier enforcement is stubbed (reads `x-tier` header /
?tier= for now) until the fullstack auth layer lands — see API_CONTRACT.md Q1.

Run:
  python -m scripts.serve_api            # binds 0.0.0.0:8000 by default
Bind/port via EDGEWIRE_API_HOST / EDGEWIRE_API_PORT.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from ..db.database import connect
from ..ingest.bootstrap import seed_if_empty
from .. import screens

# Sport enum (frontend) -> internal sport_key.
_SPORT_KEY = {
    "MLB": "baseball_mlb",
    "NFL": "americanfootball_nfl",
    "NBA": "basketball_nba",
    "NHL": "icehockey_nhl",
}

# Spec 03 §5.3 capability flags — honest about the lean data tier.
_CAPABILITIES = {
    "splits_available": False,        # no betting-splits feed contracted
    "sharp_coverage": "partial",      # Pinnacle via eu region only
    "rlm_mode": "sharp_proxy",        # true RLM needs splits; show sharp-move proxy
    "data_tier": "the_odds_api",
    "data_delay_note": "Consensus close is polled, not streamed — labeled best-effort.",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "EdgeWireAPI/0.1"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # CORS for the Vite dev server.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, x-tier, Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, x-tier, Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip("/")

        try:
            if path == "/api/health":
                return self._send(200, {"status": "ok", "service": "edgewire-api"})

            if path == "/api/capabilities":
                return self._send(200, _CAPABILITIES)

            if path == "/api/ev-screen":
                sport = qs.get("sport", [None])[0]
                sport_key = _SPORT_KEY.get(sport, None) if sport else None
                markets = tuple(qs.get("market", [])) or ("h2h", "spreads", "totals")
                conn = connect()
                data = screens.build_ev_screen(conn, sport_key=sport_key, markets=markets)
                return self._send(200, data)

            if path == "/api/clv-summary":
                window = qs.get("window", ["all"])[0]
                conn = connect()
                data = screens.build_clv_summary(conn, window=window)
                return self._send(200, data)

            return self._send(404, {"error": "not found", "path": path})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": str(exc)})

    def log_message(self, *args):  # quieter logs
        pass


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or os.environ.get("EDGEWIRE_API_HOST", "0.0.0.0")
    # Render (and most PaaS) injects the bind port via $PORT — honor it first,
    # then our local override, then the dev default. This removes any need for
    # an inline-env hack in the start command.
    if port is None:
        port = int(os.environ.get("PORT") or os.environ.get("EDGEWIRE_API_PORT", "8000"))
    else:
        port = int(port)

    # First-boot self-seed: a fresh persistent disk has an empty SQLite file, so
    # populate schema + MLB fixtures once (idempotent; no-op on a populated DB).
    # Keeps deployed endpoints returning real data immediately, no manual step.
    try:
        conn = connect()
        summary = seed_if_empty(conn)
        conn.close()
        if summary.get("seeded"):
            print(f"EdgeWire API: seeded fixtures on empty DB -> {summary.get('odds_rows')} odds rows", flush=True)
        else:
            print(f"EdgeWire API: DB already populated ({summary.get('reason')})", flush=True)
    except Exception as exc:  # noqa: BLE001 — never let seeding crash the boot
        print(f"EdgeWire API: bootstrap seed skipped ({exc})", flush=True)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"EdgeWire API listening on http://{host}:{port}", flush=True)
    httpd.serve_forever()
