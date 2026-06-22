-- EdgeWire odds time-series schema (SQLite to start; portable to Postgres).
--
-- Design goals:
--   * Capture EVERY odds observation as an immutable append-only snapshot so we
--     can reconstruct full line-movement history and compute Closing Line Value.
--   * Abstract the data provider: provider-specific ids live alongside our own
--     normalized keys, so swapping The Odds API -> OddsJam/SportsDataIO later is
--     a data-source swap, not a schema rewrite.
--   * No EV/fair-value math is stored here yet — that lands once the quant's
--     Spec 01 is finalized. This layer is purely normalized raw market data.
--
-- Grain of the core fact table (odds_snapshot): one row per
--   (event, bookmaker, market, selection, observed_at).
--
-- CLV note: we do NOT store a single "closing line" column. Closing line is
-- derived as the last snapshot at/just before commence_time. We DO flag the
-- first observation per (event,book,market,selection) as is_opening for fast
-- opening-line lookups; closing is resolved at query/compute time.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;      -- concurrent reads during ingestion writes

-- ---------------------------------------------------------------------------
-- Reference / dimension tables
-- ---------------------------------------------------------------------------

-- Sports/leagues we track. provider_sport_key mirrors The Odds API sport_key
-- (e.g. 'baseball_mlb', 'americanfootball_nfl', 'basketball_nba').
CREATE TABLE IF NOT EXISTS sport (
    id                 INTEGER PRIMARY KEY,
    sport_key          TEXT NOT NULL UNIQUE,   -- normalized internal key
    title              TEXT NOT NULL,          -- human label, e.g. "MLB"
    "group"            TEXT,                   -- e.g. "Baseball"
    active             INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Sportsbooks / bookmakers. provider_key mirrors The Odds API bookmaker key
-- (e.g. 'draftkings', 'fanduel', 'betmgm', 'pinnacle').
CREATE TABLE IF NOT EXISTS bookmaker (
    id                 INTEGER PRIMARY KEY,
    book_key           TEXT NOT NULL UNIQUE,   -- normalized internal key
    title              TEXT NOT NULL,
    region             TEXT,                   -- us, us2, eu, uk, au
    -- Pinnacle/Circa etc. are "sharp" books used as fair-value anchors.
    is_sharp           INTEGER NOT NULL DEFAULT 0,
    active             INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Market types. Mirrors The Odds API market keys.
--   h2h = moneyline, spreads = point spread, totals = over/under,
--   plus props (player_pass_tds, batter_home_runs, ...) added as discovered.
CREATE TABLE IF NOT EXISTS market_type (
    id                 INTEGER PRIMARY KEY,
    market_key         TEXT NOT NULL UNIQUE,   -- 'h2h','spreads','totals',...
    title              TEXT NOT NULL,
    -- has_line: spreads/totals carry a 'point'; h2h does not.
    has_line           INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ---------------------------------------------------------------------------
-- Events (games)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
    id                 INTEGER PRIMARY KEY,
    -- Provider's stable event id (The Odds API "id"). Unique per provider.
    provider           TEXT NOT NULL,
    provider_event_id  TEXT NOT NULL,
    sport_id           INTEGER NOT NULL REFERENCES sport(id),
    commence_time      TEXT NOT NULL,          -- ISO8601 UTC; CLV cutoff anchor
    home_team          TEXT NOT NULL,
    away_team          TEXT NOT NULL,
    -- Lifecycle: scheduled -> live -> final. Scores fill in once available.
    status             TEXT NOT NULL DEFAULT 'scheduled',
    completed          INTEGER NOT NULL DEFAULT 0,
    home_score         INTEGER,
    away_score         INTEGER,
    first_seen_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (provider, provider_event_id)
);

CREATE INDEX IF NOT EXISTS idx_event_sport_commence
    ON event (sport_id, commence_time);
CREATE INDEX IF NOT EXISTS idx_event_commence
    ON event (commence_time);

-- ---------------------------------------------------------------------------
-- Odds snapshots — the append-only time-series fact table
-- ---------------------------------------------------------------------------
-- One row = one observed price for one selection at one book at one instant.
-- We never UPDATE prices; each ingestion run INSERTs new rows when the price
-- (or line) differs from the most recent observation for that key. This gives
-- us full movement history and an auditable trail for CLV.
CREATE TABLE IF NOT EXISTS odds_snapshot (
    id                 INTEGER PRIMARY KEY,
    event_id           INTEGER NOT NULL REFERENCES event(id),
    bookmaker_id       INTEGER NOT NULL REFERENCES bookmaker(id),
    market_type_id     INTEGER NOT NULL REFERENCES market_type(id),

    -- Selection within the market:
    --   h2h     -> team name (or "Draw")
    --   spreads -> team name, with point = the spread (e.g. -1.5)
    --   totals  -> "Over"/"Under", with point = the total (e.g. 8.5)
    --   props   -> player/selection name, point = the prop line, plus desc
    selection          TEXT NOT NULL,
    description        TEXT,                   -- player name for props, else NULL
    point              REAL,                   -- line value; NULL for h2h

    -- Price as American odds (integer, e.g. -110, +145). Canonical storage.
    price_american     INTEGER NOT NULL,
    -- Decimal odds cached for convenience (derived; kept for fast EV math later).
    price_decimal      REAL NOT NULL,

    -- When the book last updated this market (from provider), and when WE saw it.
    book_last_update   TEXT,                   -- provider 'last_update'
    observed_at        TEXT NOT NULL,          -- our ingestion snapshot time (UTC)

    -- Market suspended/unavailable at this observation. Spec 02 §4.1 requires
    -- this so the closing-snapshot builder can EXCLUDE suspended quotes (a
    -- suspension is not a price). The Odds API omits suspended markets rather
    -- than flagging them, so this is 0 for live data today, but the column is
    -- here so a premium feed (which does flag suspension) is a capture-layer swap.
    is_suspended       INTEGER NOT NULL DEFAULT 0,

    -- True only for the first observation of this selection (fast opening lookup).
    is_opening         INTEGER NOT NULL DEFAULT 0,

    -- Provenance: which ingestion run produced this row.
    ingest_run_id      INTEGER REFERENCES ingest_run(id)
);

-- Movement reconstruction & CLV queries hit this index hard.
CREATE INDEX IF NOT EXISTS idx_snapshot_line
    ON odds_snapshot (event_id, market_type_id, bookmaker_id, selection, observed_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_observed
    ON odds_snapshot (observed_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_opening
    ON odds_snapshot (event_id, market_type_id, bookmaker_id, selection)
    WHERE is_opening = 1;

-- ---------------------------------------------------------------------------
-- Ingestion provenance — one row per ingestion run for auditability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_run (
    id                 INTEGER PRIMARY KEY,
    provider           TEXT NOT NULL,
    sport_key          TEXT,
    started_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at        TEXT,
    status             TEXT NOT NULL DEFAULT 'running',  -- running|ok|error
    events_seen        INTEGER NOT NULL DEFAULT 0,
    snapshots_written  INTEGER NOT NULL DEFAULT 0,
    -- Quota accounting for paid APIs (The Odds API returns these as headers).
    requests_used      INTEGER,
    requests_remaining INTEGER,
    note               TEXT
);

-- ---------------------------------------------------------------------------
-- Derived / spec-driven tables
--
-- These are populated by COMPUTE modules built strictly against the quant's
-- methodology specs. The raw market data above is provider-fed; the tables
-- below hold spec outputs. They are defined here (additive, never altering
-- odds_snapshot) so the schema is migration-stable as those modules land.
--   * movement_point / movement_signal  — Spec 03 §5.2 (line movement, steam)
--   * bet_signal                         — Spec 02 §4.2 (CLV gradable record)
-- The math that fills them is intentionally NOT implemented yet.
-- ---------------------------------------------------------------------------

-- Per-outcome consensus movement series (materialized for fast UI / charts).
-- Filled by the Spec 01 consensus pipeline (de-vig -> staleness -> outlier ->
-- weighted average -> renormalize). consensus_* values are no-vig.
CREATE TABLE IF NOT EXISTS movement_point (
    id                  INTEGER PRIMARY KEY,
    event_id            INTEGER NOT NULL REFERENCES event(id),
    market_type_id      INTEGER NOT NULL REFERENCES market_type(id),
    selection           TEXT NOT NULL,
    point               REAL,
    observed_at         TEXT NOT NULL,
    consensus_fair_prob REAL NOT NULL,          -- Spec 01 §3 (no-vig)
    consensus_american  INTEGER NOT NULL,
    n_books             INTEGER NOT NULL,
    confidence          TEXT NOT NULL            -- high|medium|low
);
CREATE INDEX IF NOT EXISTS idx_movement_point_series
    ON movement_point (event_id, market_type_id, selection, observed_at);

-- Fired movement signals (steam / sharp-move / rlm). Append-only, auditable.
-- RLM columns stay NULL until a betting-splits feed is contracted (Spec 03 §3.1).
CREATE TABLE IF NOT EXISTS movement_signal (
    id                  INTEGER PRIMARY KEY,
    event_id            INTEGER NOT NULL REFERENCES event(id),
    market_type_id      INTEGER NOT NULL REFERENCES market_type(id),
    selection           TEXT NOT NULL,
    point               REAL,
    signal_type         TEXT NOT NULL,           -- 'steam'|'sharp_move'|'rlm'
    direction           TEXT NOT NULL,           -- 'toward'|'away' vs selection
    magnitude_prob      REAL NOT NULL,           -- no-vig prob delta that triggered
    window_seconds      INTEGER NOT NULL,
    n_books_moved       INTEGER NOT NULL,
    books_total         INTEGER NOT NULL,
    sharp_led           INTEGER,                 -- bool, nullable
    ticket_pct          REAL,                    -- RLM-only, NULL w/o splits feed
    handle_pct          REAL,                    -- RLM-only, NULL w/o splits feed
    splits_source       TEXT,                    -- RLM-only
    detected_at         TEXT NOT NULL,
    detail_json         TEXT                     -- thresholds + per-book deltas
);
CREATE INDEX IF NOT EXISTS idx_movement_signal_event
    ON movement_signal (event_id, signal_type, detected_at);

-- CLV gradable record (Spec 02 §4.2). Append-only / immutable: a regrade writes
-- a NEW versioned row (bet_id + grade_version) and keeps the old one — the
-- auditable ledger is the trust moat. clv_* fields fill in at grading time.
CREATE TABLE IF NOT EXISTS bet_signal (
    id                       INTEGER PRIMARY KEY,
    bet_id                   TEXT NOT NULL,       -- stable id across regrades
    grade_version            INTEGER NOT NULL DEFAULT 1,
    user_id                  TEXT,                -- NULL for a pure EdgeWire signal
    event_id                 INTEGER NOT NULL REFERENCES event(id),
    sport_key                TEXT NOT NULL,
    market_key               TEXT NOT NULL,
    line                     REAL,
    outcome                  TEXT NOT NULL,
    logged_at_utc            TEXT NOT NULL,
    bet_book                 TEXT,
    bet_decimal              REAL NOT NULL,
    bet_american             INTEGER NOT NULL,
    fair_prob_at_bet         REAL,                -- Spec 01 consensus at log time
    ev_pct_at_bet            REAL,                -- Spec 01 forward EV at log time
    -- ---- filled at grading (post-close), Spec 02 §2 ----
    event_start_utc          TEXT,
    closing_consensus_fair_prob REAL,
    closing_fair_american    INTEGER,
    n_books_close            INTEGER,
    close_confidence         TEXT,
    bet_book_open_at_close    INTEGER,
    clv_prob                 REAL,                -- §2.1
    beat_close               INTEGER,             -- §2.2 (bool)
    clv_pct                  REAL,                -- §2.3
    clv_cents                INTEGER,             -- display
    clv_status               TEXT NOT NULL DEFAULT 'pending',
        -- pending|graded|ungraded_no_close|ungraded_postponed|clv_not_applicable
    devig_method             TEXT,
    graded_at_utc            TEXT,
    UNIQUE (bet_id, grade_version)
);
CREATE INDEX IF NOT EXISTS idx_bet_signal_event   ON bet_signal (event_id);
CREATE INDEX IF NOT EXISTS idx_bet_signal_status  ON bet_signal (clv_status);

-- ---------------------------------------------------------------------------
-- Convenience views
-- ---------------------------------------------------------------------------

-- Latest observed price per (event, book, market, selection).
CREATE VIEW IF NOT EXISTS v_latest_odds AS
SELECT s.*
FROM odds_snapshot s
JOIN (
    SELECT event_id, bookmaker_id, market_type_id, selection,
           MAX(observed_at) AS max_obs
    FROM odds_snapshot
    GROUP BY event_id, bookmaker_id, market_type_id, selection
) latest
  ON  s.event_id       = latest.event_id
  AND s.bookmaker_id   = latest.bookmaker_id
  AND s.market_type_id = latest.market_type_id
  AND s.selection      = latest.selection
  AND s.observed_at    = latest.max_obs;
