#!/usr/bin/env python3
"""Run the EdgeWire HTTP API (fixture-backed).

Usage:
  python scripts/serve_api.py                  # 0.0.0.0:8000
  EDGEWIRE_API_PORT=8000 python scripts/serve_api.py

Make sure the DB is populated first:
  python scripts/run_ingest.py --init
  python scripts/run_ingest.py --sport baseball_mlb --source fixture
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edgewire.apiserver.server import serve

if __name__ == "__main__":
    serve()
