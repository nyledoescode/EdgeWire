import type {
  EvScreenResponse,
  ClvSummary,
  EventRow,
  MovementPoint,
  BookPrice,
  Capabilities,
  MovementSignal,
} from '../types'

// ---------------------------------------------------------------------------
// MOCK DATA. Illustrative only — these are not real odds and not advice.
// Shapes mirror src/types.ts so the live API can drop in with no UI changes.
//
// Per Spec 03 (§0): movement is measured in NO-VIG CONSENSUS PROBABILITY space,
// not raw price. Each movement series carries `consensusFairProb`, and the
// open->now delta the UI shows is the fair-prob delta — a lengthening price can
// still mean the fair moved AGAINST the side, so price alone would mislead.
// ---------------------------------------------------------------------------

const BOOKS = [
  { book: 'draftkings', bookName: 'DraftKings' },
  { book: 'fanduel', bookName: 'FanDuel' },
  { book: 'betmgm', bookName: 'BetMGM' },
  { book: 'caesars', bookName: 'Caesars' },
  { book: 'pointsbet', bookName: 'PointsBet' },
]

const now = Date.now()
const iso = (msAgo: number) => new Date(now - msAgo).toISOString()
const isoAhead = (msAhead: number) => new Date(now + msAhead).toISOString()

// American odds -> implied prob (with vig)
function impliedProb(american: number): number {
  return american > 0 ? 100 / (american + 100) : -american / (-american + 100)
}
// fair prob -> fair american odds
function probToAmerican(p: number): number {
  if (p <= 0 || p >= 1) return 0
  return p >= 0.5
    ? Math.round((-100 * p) / (1 - p))
    : Math.round((100 * (1 - p)) / p)
}
// EV of betting bestPrice given fair prob p
function evOf(p: number, american: number): number {
  const dec = american > 0 ? american / 100 + 1 : 100 / -american + 1
  return p * (dec - 1) - (1 - p)
}

/**
 * Build a movement series in no-vig prob space. `probSteps` are the consensus
 * fair-prob values oldest->newest; price for display is derived from each prob.
 */
function buildMovement(probSteps: number[], point: number | null): MovementPoint[] {
  const n = probSteps.length
  return probSteps.map((p, i) => ({
    t: iso((n - i) * 60 * 60 * 1000),
    consensusFairProb: +p.toFixed(4),
    price: probToAmerican(p),
    point,
  }))
}

function priceSet(
  outcomeName: string,
  prices: number[],
  point: number | null,
  fairProb: number,
  /** Consensus fair-prob series (oldest->newest); last should ≈ fairProb. */
  probSteps?: number[],
) {
  const bookPrices: BookPrice[] = prices.map((price, i) => ({
    ...BOOKS[i],
    price,
    point,
    updatedAt: iso(Math.floor(Math.random() * 30 * 60 * 1000)),
  }))
  // best = highest american value (best payout)
  let bestIdx = 0
  bookPrices.forEach((bp, i) => {
    if (bp.price > bookPrices[bestIdx].price) bestIdx = i
  })
  bookPrices[bestIdx] = { ...bookPrices[bestIdx], isBest: true }
  const best = bookPrices[bestIdx]

  // Default series gently converges to fairProb if not supplied.
  const series = probSteps ?? [fairProb - 0.02, fairProb - 0.005, fairProb + 0.01, fairProb]
  const movement = buildMovement(series, point)

  const pOpen = movement[0].consensusFairProb ?? fairProb
  const pNow = movement[movement.length - 1].consensusFairProb ?? fairProb
  const fairProbDeltaPp = +((pNow - pOpen) * 100).toFixed(2)
  const americanDelta = probToAmerican(pNow) - probToAmerican(pOpen)

  const ev = evOf(fairProb, best.price)
  // confidence by book coverage (Spec 01 §3 confidence tiers, simplified)
  const confidence: 'high' | 'medium' | 'low' =
    bookPrices.length >= 5 ? 'high' : bookPrices.length >= 3 ? 'medium' : 'low'
  // server-side +EV gate: positive EV AND not low-confidence (Spec 01 §4.3)
  const isPlusEv = ev > 0 && confidence !== 'low'

  return {
    name: outcomeName,
    fairProb,
    fairPrice: probToAmerican(fairProb),
    bestPrice: best.price,
    bestBook: best.book,
    ev,
    confidence,
    isPlusEv,
    stale: false,
    prices: bookPrices,
    movement,
    fairProbDeltaPp,
    americanDelta,
    lineMovePoints: null,
  }
}


const events: EventRow[] = [
  {
    id: 'evt_nfl_kc_buf',
    sport: 'NFL',
    league: 'NFL',
    startTime: isoAhead(6 * 60 * 60 * 1000),
    homeTeam: 'Kansas City Chiefs',
    awayTeam: 'Buffalo Bills',
    trackedFrom: iso(20 * 60 * 60 * 1000),
    // Steam onto the dog (BUF) — broad, fast, sharp-led. Context, not a tip.
    signals: [
      {
        type: 'steam',
        selection: 'Buffalo Bills',
        direction: 'toward',
        magnitudePp: 5.1,
        windowSeconds: 8 * 60,
        nBooksMoved: 6,
        booksTotal: 8,
        sharpLed: true,
        detectedAt: iso(40 * 60 * 1000),
      },
    ],
    markets: [
      {
        type: 'h2h',
        label: 'Moneyline',
        outcomes: [
          priceSet('Kansas City Chiefs', [-110, -118, -115, -112, -120], null, 0.55, [0.58, 0.575, 0.56, 0.55]),
          priceSet('Buffalo Bills', [-105, +102, -108, +100, -110], null, 0.45, [0.42, 0.425, 0.44, 0.45]),
        ],
      },
      {
        type: 'spreads',
        label: 'Spread',
        outcomes: [
          priceSet('Kansas City Chiefs -1.5', [-110, -108, -112, -110, -115], -1.5, 0.52),
          priceSet('Buffalo Bills +1.5', [-110, -112, -108, -110, -105], 1.5, 0.48),
        ],
      },
    ],
  },
  {
    id: 'evt_nba_bos_den',
    sport: 'NBA',
    league: 'NBA',
    startTime: isoAhead(3 * 60 * 60 * 1000),
    homeTeam: 'Denver Nuggets',
    awayTeam: 'Boston Celtics',
    trackedFrom: iso(14 * 60 * 60 * 1000),
    // Sharp books led the Under; soft books lagging. Honest price-only signal.
    signals: [
      {
        type: 'sharp_move',
        selection: 'Under 224.5',
        direction: 'toward',
        magnitudePp: 3.0,
        windowSeconds: 12 * 60,
        nBooksMoved: 3,
        booksTotal: 9,
        sharpLed: true,
        detectedAt: iso(25 * 60 * 1000),
      },
    ],
    markets: [
      {
        type: 'h2h',
        label: 'Moneyline',
        outcomes: [
          priceSet('Denver Nuggets', [+105, +110, +102, +108, +100], null, 0.50),
          priceSet('Boston Celtics', [-125, -130, -122, -128, -120], null, 0.50),
        ],
      },
      {
        type: 'totals',
        label: 'Total',
        outcomes: [
          // Spec 03 §1.3 worked example: Over PRICE lengthened (-110 -> +104) but
          // the no-vig FAIR moved AGAINST Over (0.500 -> 0.470). The ▲/▼ must
          // follow the fair-prob delta (▼), not be fooled by the longer price.
          priceSet('Over 224.5', [-110, -108, +104, -105, -110], 224.5, 0.47, [0.500, 0.492, 0.480, 0.470]),
          priceSet('Under 224.5', [-110, -112, -124, -115, -110], 224.5, 0.53, [0.500, 0.508, 0.520, 0.530]),
        ],
      },
    ],
  },
  {
    id: 'evt_mlb_lad_nyy',
    sport: 'MLB',
    league: 'MLB',
    startTime: isoAhead(9 * 60 * 60 * 1000),
    homeTeam: 'New York Yankees',
    awayTeam: 'Los Angeles Dodgers',
    trackedFrom: iso(30 * 60 * 60 * 1000),
    markets: [
      {
        type: 'h2h',
        label: 'Moneyline',
        outcomes: [
          priceSet('New York Yankees', [-115, -120, -118, -110, -122], null, 0.51),
          { ...priceSet('Los Angeles Dodgers', [-105, +100, -102, +104, -108], null, 0.49), stale: true },
        ],
      },
    ],
  },
  {
    id: 'evt_nhl_col_edm',
    sport: 'NHL',
    league: 'NHL',
    startTime: isoAhead(5 * 60 * 60 * 1000),
    homeTeam: 'Edmonton Oilers',
    awayTeam: 'Colorado Avalanche',
    trackedFrom: iso(16 * 60 * 60 * 1000),
    markets: [
      {
        type: 'h2h',
        label: 'Moneyline',
        outcomes: [
          priceSet('Edmonton Oilers', [+120, +128, +115, +124, +118], null, 0.46),
          priceSet('Colorado Avalanche', [-140, -148, -135, -142, -138], null, 0.54),
        ],
      },
    ],
  },
]

// Capability flags (Spec 03 §5.3). On The Odds API budget tier we have NO
// betting-splits feed, so rlmMode is 'sharp_proxy' and splitsAvailable=false.
// The UI must NOT fabricate public ticket/handle percentages off these.
const capabilities: Capabilities = {
  splitsAvailable: false,
  sharpCoverage: 'partial',
  rlmMode: 'sharp_proxy',
  steamFidelity: 'coarse',
}

export const mockEvScreen: EvScreenResponse = {
  generatedAt: new Date(now).toISOString(),
  capabilities,
  events,
}

// Re-export signal type usage so tooling keeps MovementSignal referenced.
export type { MovementSignal }


// ---- CLV / track record mock ----

const clvRecords = [
  { sport: 'NFL', event: 'KC @ BUF', market: 'Spread', selection: 'KC -1.5', taken: -108, close: -120, result: 'win' as const },
  { sport: 'NBA', event: 'BOS @ DEN', market: 'Total', selection: 'Over 224.5', taken: -105, close: -114, result: 'loss' as const },
  { sport: 'MLB', event: 'LAD @ NYY', market: 'ML', selection: 'NYY', taken: +104, close: -112, result: 'win' as const },
  { sport: 'NHL', event: 'COL @ EDM', market: 'ML', selection: 'COL', taken: -135, close: -150, result: 'win' as const },
  { sport: 'NBA', event: 'MIA @ MIL', market: 'Spread', selection: 'MIA +3.5', taken: +100, close: -108, result: 'push' as const },
  // Not every flagged edge beats the close — we publish those too. Honesty is the moat.
  { sport: 'NFL', event: 'DAL @ PHI', market: 'ML', selection: 'DAL', taken: +145, close: +162, result: 'loss' as const },
  { sport: 'MLB', event: 'HOU @ SEA', market: 'Total', selection: 'Under 7.5', taken: -110, close: -118, result: 'win' as const },
  { sport: 'NBA', event: 'PHX @ SAC', market: 'Spread', selection: 'PHX -2.5', taken: -106, close: -101, result: 'loss' as const },
  { sport: 'NHL', event: 'TOR @ BOS', market: 'Total', selection: 'Over 6', taken: +102, close: -110, result: 'win' as const },
  { sport: 'NBA', event: 'LAL @ GSW', market: 'ML', selection: 'GSW', taken: -120, close: -132, result: 'pending' as const },
]

function clvPct(taken: number, close: number): number {
  // Difference in no-vig implied prob, expressed in percentage points.
  return +((impliedProb(close) - impliedProb(taken)) * 100).toFixed(2)
}

const records = clvRecords.map((r, i) => {
  const clv = clvPct(r.taken, r.close)
  return {
    id: `clv_${i + 1}`,
    placedAt: iso((i + 1) * 26 * 60 * 60 * 1000),
    sport: r.sport as ClvSummary['records'][number]['sport'],
    event: r.event,
    market: r.market,
    selection: r.selection,
    takenPrice: r.taken,
    closingPrice: r.close,
    clvPct: clv,
    result: r.result,
  }
})

const graded = records.filter((r) => r.result !== 'pending')
const beat = graded.filter((r) => r.clvPct > 0).length
const n = graded.length

// Wilson 95% CI for a proportion (Spec 02 §3.2) — honest interval, not normal
// approximation which misbehaves at small n / extreme rates.
function wilsonCI(successes: number, total: number): [number, number] {
  if (total === 0) return [0, 0]
  const z = 1.96
  const p = successes / total
  const z2 = z * z
  const denom = 1 + z2 / total
  const center = (p + z2 / (2 * total)) / denom
  const margin =
    (z * Math.sqrt((p * (1 - p)) / total + z2 / (4 * total * total))) / denom
  return [+Math.max(0, center - margin).toFixed(3), +Math.min(1, center + margin).toFixed(3)]
}

// t-based 95% CI for the mean CLV% (small-sample appropriate).
function meanCI(values: number[]): [number, number] {
  const k = values.length
  if (k < 2) return [0, 0]
  const mean = values.reduce((s, v) => s + v, 0) / k
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / (k - 1)
  const se = Math.sqrt(variance / k)
  const t = 2.0 // ~t_0.975 for small df; backend uses exact df
  return [+(mean - t * se).toFixed(2), +(mean + t * se).toFixed(2)]
}

// Display gate (Spec 02 §3.3): never headline a sub-30 sample.
function gateFor(size: number): ClvSummary['displayGate'] {
  if (size < 10) return 'building'
  if (size < 30) return 'small_sample'
  if (size < 100) return 'full'
  return 'verified'
}

const clvValues = graded.map((r) => r.clvPct)

export const mockClvSummary: ClvSummary = {
  sampleSize: n,
  beatRate: n ? +(beat / n).toFixed(3) : 0,
  beatRateCI95: wilsonCI(beat, n),
  avgClvPct: n ? +(clvValues.reduce((s, v) => s + v, 0) / n).toFixed(2) : 0,
  avgClvPctCI95: meanCI(clvValues),
  displayGate: gateFor(n),
  window: 'last 90 days (illustrative sample)',
  generatedAt: new Date(now).toISOString(),
  records,
}
