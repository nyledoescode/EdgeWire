import { fetchEvScreen } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { useTier } from '../auth/TierContext'
import { Sparkline } from '../components/Sparkline'
import { PaywallCard } from '../components/Paywall'
import { SignalsStrip, RlmModeNote } from '../components/Signals'
import { fmtAmerican, fmtProbDeltaPp, relTime, fmtTime } from '../lib/format'
import type { Outcome } from '../types'

/**
 * The ▲/▼ direction comes from the CONSENSUS NO-VIG FAIR PROBABILITY delta
 * (Spec 03 §1.2), NOT raw price. A lengthening price can still mean the fair
 * moved against the side, so price alone would mislead. We show the American
 * "cents" move as a secondary, de-emphasized figure.
 */
function MoveRow({ o }: { o: Outcome }) {
  const probDelta = o.fairProbDeltaPp ?? 0
  const up = probDelta >= 0
  const firstPrice = o.movement[0]?.price ?? o.bestPrice
  const lastPrice = o.movement[o.movement.length - 1]?.price ?? o.bestPrice
  const americanDelta = o.americanDelta ?? lastPrice - firstPrice

  return (
    <div className="move-row">
      <div className="move-name">{o.name}</div>
      <Sparkline points={o.movement} width={120} height={28} />
      <div className="move-stats">
        {/* PRIMARY: fair-prob direction */}
        <span className={up ? 'move-delta up' : 'move-delta down'} title="Consensus no-vig fair probability move (open→now)">
          {up ? '▲' : '▼'} {fmtProbDeltaPp(Math.abs(probDelta))} fair
        </span>
        {/* SECONDARY: raw american cents, de-emphasized */}
        <span className="move-cents" title="Raw price move (display only)">
          {fmtAmerican(firstPrice)} → {fmtAmerican(lastPrice)}
          {americanDelta !== 0 && (
            <em>{` (${americanDelta > 0 ? '+' : ''}${americanDelta}¢)`}</em>
          )}
        </span>
      </div>
    </div>
  )
}

export function Movement() {
  const { has } = useTier()
  const { data, loading, error } = useAsync(fetchEvScreen, [])

  if (!has('pro')) {
    return (
      <section>
        <div className="page-head">
          <h1>Line Movement</h1>
        </div>
        <PaywallCard required="pro" feature="Line movement tracking" />
      </section>
    )
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Line Movement</h1>
          <p className="lede">
            Open → now tracking in <strong>no-vig fair-probability</strong> space —
            the honest direction of the market, not just a longer or shorter price.
            Steam and sharp-move signals are context, never a signal to chase.
          </p>
        </div>
        {data && <div className="freshness">Updated {relTime(data.generatedAt)}</div>}
      </div>

      {data && <RlmModeNote caps={data.capabilities} />}

      {loading && <div className="state">Loading movement…</div>}
      {error && <div className="state state-error">Couldn’t load: {error}</div>}

      <div className="move-grid">
        {data?.events.map((ev) => {
          const ml = ev.markets.find((m) => m.type === 'h2h') ?? ev.markets[0]
          return (
            <div key={ev.id} className="move-card">
              <div className="move-card-head">
                <span className="sport-chip">{ev.sport}</span>
                <span className="move-matchup">{ev.awayTeam} @ {ev.homeTeam}</span>
              </div>
              {ev.trackedFrom && (
                <div className="tracked-from" title="We can only call 'open' the earliest snapshot we captured">
                  Tracked from {fmtTime(ev.trackedFrom)}
                </div>
              )}
              <SignalsStrip signals={ev.signals} />
              {ml.outcomes.map((o) => (
                <MoveRow key={o.name} o={o} />
              ))}
            </div>
          )
        })}
      </div>

      <p className="disclaimer">
        Movement reflects market activity, not a recommendation or a guaranteed
        outcome. Everything is probability and expected value. Bet responsibly.
      </p>
    </section>
  )
}
