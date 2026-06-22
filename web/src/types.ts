// EdgeWire shared data contract (frontend view).
// These types describe exactly what the web app expects from the backend
// intelligence API. The backend engineer should align response shapes to
// these, or document deltas in API_CONTRACT.md so wiring stays trivial.
//
// All odds are American odds (e.g. -110, +145). Probabilities are 0..1.
// Timestamps are ISO-8601 strings (UTC).

export type Sport = 'NFL' | 'NBA' | 'MLB' | 'NHL' | 'NCAAF' | 'NCAAB' | 'SOCCER'

export type MarketType = 'h2h' | 'spreads' | 'totals'

export type Tier = 'free' | 'pro' | 'elite'

/** A single sportsbook's price for one outcome of one market. */
export interface BookPrice {
  /** Stable sportsbook key, e.g. "draftkings", "fanduel", "betmgm". */
  book: string
  /** Display name, e.g. "DraftKings". */
  bookName: string
  /** American odds for this outcome at this book. */
  price: number
  /** Point/line for spreads & totals (e.g. -3.5, 47.5). Null for h2h. */
  point: number | null
  /** When this price was last observed. */
  updatedAt: string
  /** True if this book offers the best (highest) price for the outcome. */
  isBest?: boolean
}

/** One betem outcome (e.g. the "Home" side of a spread) priced across books. */
export interface Outcome {
  /** Outcome label, e.g. "Kansas City Chiefs", "Over", "Under". */
  name: string
  /** No-vig fair probability for this outcome (0..1), from quant model. */
  fairProb: number
  /** Fair American odds implied by fairProb. */
  fairPrice: number
  /** Best available American odds across all books for this outcome. */
  bestPrice: number
  /** Book key offering the best price. */
  bestBook: string
  /** Expected value vs fair, as a fraction (0.042 = +4.2% EV). */
  ev: number
  /**
   * Consensus confidence (Spec 01 §5). The +EV badge is only highlighted when
   * isPlusEv === true AND confidence !== 'low' (Spec 01 §4.3 gate).
   */
  confidence?: 'high' | 'medium' | 'low'
  /** Server-side +EV gate result (Spec 01). Authoritative; UI must not re-derive. */
  isPlusEv?: boolean
  /** True if the best price is from a stale book observation — flag, don't trust. */
  stale?: boolean
  /** All book prices for this outcome. */
  prices: BookPrice[]
  /** Recent movement series for this outcome (sparkline). Oldest -> newest. */
  movement: MovementPoint[]
  /**
   * Open->now movement of the CONSENSUS no-vig fair probability, in percentage
   * points (Spec 03 §1.2). Positive = market moved TOWARD this outcome (became
   * more likely / fair price shortened). This is the HONEST direction — a
   * lengthening price can still mean the fair moved against the side, so the
   * UI's ▲/▼ must read from this, not from raw price. Null until backend emits.
   */
  fairProbDeltaPp?: number | null
  /** Open->now raw American "cents" move, for secondary display only. */
  americanDelta?: number | null
  /** Point/line move in points (spread/total number move), signed. */
  lineMovePoints?: number | null
}

/**
 * One observation on a movement series. Per Spec 03 §0, movement is measured in
 * no-vig consensus probability space; `price` is kept for the "cents" display.
 */
export interface MovementPoint {
  t: string // ISO timestamp
  /** Consensus no-vig fair probability at this time (0..1). Primary signal. */
  consensusFairProb?: number | null
  /** Consensus American odds at this time (display). */
  price: number
  point?: number | null
}

// ---- Line-movement signals (Spec 03 §2-§4) ----

export type SignalType = 'steam' | 'sharp_move' | 'rlm'

/**
 * A fired market-movement signal. Always context, never a recommendation.
 * RLM-only fields (ticketPct/handlePct) are null unless a real splits feed is
 * contracted — we NEVER fabricate public percentages.
 */
export interface MovementSignal {
  type: SignalType
  selection: string
  /** Direction relative to the selection. */
  direction: 'toward' | 'away'
  /** No-vig prob delta (pp) that triggered it. */
  magnitudePp: number
  windowSeconds: number
  nBooksMoved: number
  booksTotal: number
  /** Whether sharp books led the move (nullable). */
  sharpLed?: boolean | null
  /** RLM-only, null without a splits feed. */
  ticketPct?: number | null
  handlePct?: number | null
  splitsSource?: string | null
  detectedAt: string
}

/** A market (h2h / spread / total) for one event, with its outcomes. */
export interface Market {
  type: MarketType
  /** Human label, e.g. "Moneyline", "Spread", "Total". */
  label: string
  outcomes: Outcome[]
}

/** A bettable event/game with its markets. */
export interface EventRow {
  id: string
  sport: Sport
  league: string
  /** Scheduled start time. */
  startTime: string
  homeTeam: string
  awayTeam: string
  markets: Market[]
  /** Fired movement signals for this event (steam / sharp-move / rlm). */
  signals?: MovementSignal[]
  /**
   * Earliest snapshot we actually captured for this event (Spec 03 §1.1).
   * Lets the UI honestly label "tracked from {time}" rather than implying we
   * caught the literal opening line. Null until backend emits.
   */
  trackedFrom?: string | null
}

/**
 * Data-source capability flags (Spec 03 §5.3). The UI degrades gracefully off
 * these so we never fabricate data we don't have (e.g. public ticket %).
 */
export interface Capabilities {
  /** True once a real betting-splits feed is contracted. */
  splitsAvailable: boolean
  /** Sharp-book (Pinnacle/Circa) coverage for the sharp-move signal. */
  sharpCoverage: 'full' | 'partial' | 'none'
  /**
   * 'true_rlm' once splits exist; otherwise 'sharp_proxy' — the UI shows the
   * labeled Sharp-Move proxy instead of fabricated public percentages.
   */
  rlmMode: 'true_rlm' | 'sharp_proxy'
  /** Steam detection fidelity given polling cadence (budget tier = coarse). */
  steamFidelity?: 'fine' | 'coarse'
}

/** The EV screen payload. */
export interface EvScreenResponse {
  generatedAt: string
  capabilities: Capabilities
  events: EventRow[]
}

// ---- CLV / track record (trust moat) ----

/** A single graded bet used to compute CLV honestly & auditably. */
export interface ClvRecord {
  id: string
  placedAt: string
  sport: Sport
  event: string
  market: string
  selection: string
  /** Odds we flagged / "bet". */
  takenPrice: number
  /** Closing odds at the book at game time. */
  closingPrice: number
  /** CLV in percentage points (positive = beat the close). */
  clvPct: number
  /** Outcome once graded: pending until settled. */
  result: 'win' | 'loss' | 'push' | 'pending'
}

export interface ClvSummary {
  /** Total graded plays in sample. */
  sampleSize: number
  /** Share of plays that beat the closing line (0..1). */
  beatRate: number
  /**
   * 95% confidence interval for beatRate (Wilson), as [lo, hi] in 0..1.
   * BINDING (Spec 02 §3.2): a beat-rate must NEVER be shown without its CI + n.
   */
  beatRateCI95?: [number, number]
  /** Average CLV in percentage points across the sample. */
  avgClvPct: number
  /** 95% CI for avgClvPct (t-based), as [lo, hi] in percentage points. */
  avgClvPctCI95?: [number, number]
  /**
   * Display gate (Spec 02 §3.3). Controls how honestly we present the sample:
   * - 'building'    : too few plays — don't headline a rate yet.
   * - 'small_sample': < 30 graded — show but soft-label as preliminary.
   * - 'full'        : sufficient sample to present normally.
   * - 'verified'    : large, independently-auditable sample.
   */
  displayGate?: 'building' | 'small_sample' | 'full' | 'verified'
  /** Window the summary covers, e.g. "last 90 days". */
  window: string
  /** When this was computed. */
  generatedAt: string
  records: ClvRecord[]
}
