import { useMemo, useState } from 'react'
import { fetchEvScreen } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { useTier } from '../auth/TierContext'
import { Sparkline } from '../components/Sparkline'
import { LockChip } from '../components/Paywall'
import { fmtAmerican, fmtEv, fmtPct, fmtTime, relTime } from '../lib/format'
import type { EventRow, MarketType, Outcome } from '../types'

const MARKET_TABS: { key: MarketType; label: string }[] = [
  { key: 'h2h', label: 'Moneyline' },
  { key: 'spreads', label: 'Spread' },
  { key: 'totals', label: 'Total' },
]

function evClass(ev: number): string {
  if (ev >= 0.03) return 'ev ev-strong'
  if (ev > 0) return 'ev ev-pos'
  return 'ev ev-neg'
}

function OutcomeRow({ o, event }: { o: Outcome; event: EventRow }) {
  const { has } = useTier()
  const canSeeMovement = has('pro')
  // Use the server-side +EV gate (Spec 01 §4.3) when present: positive EV AND
  // not low-confidence. Fall back to ev>0 only if the flag is absent.
  const highlightEv = o.isPlusEv ?? o.ev > 0
  const confidence = o.confidence

  return (
    <tr className={highlightEv ? 'row-ev' : ''}>
      <td className="cell-outcome">
        <div className="outcome-name">
          {o.name}
          {o.stale && (
            <span className="stale-chip" title="Best price is from a stale book observation — may have moved">
              stale
            </span>
          )}
        </div>
        <div className="outcome-meta">{event.awayTeam} @ {event.homeTeam}</div>
      </td>
      <td className="cell-fair">
        <div>{fmtAmerican(o.fairPrice)}</div>
        <div className="muted">
          {fmtPct(o.fairProb, 1)}
          {confidence && <span className={`conf conf-${confidence}`} title={`Consensus confidence: ${confidence}`}>{confidence[0].toUpperCase()}</span>}
        </div>
      </td>
      <td className="cell-best">
        <div className="best-price">{fmtAmerican(o.bestPrice)}</div>
        <div className="muted">{o.prices.find((p) => p.book === o.bestBook)?.bookName ?? o.bestBook}</div>
      </td>
      <td>
        {highlightEv ? (
          <span className={evClass(o.ev)} title="Expected value vs no-vig fair price">
            {fmtEv(o.ev)} EV
          </span>
        ) : (
          <span className="ev ev-neg">{fmtEv(o.ev)}</span>
        )}
      </td>
      <td className="cell-books">
        <div className="book-grid">
          {o.prices.map((p) => (
            <span key={p.book} className={p.isBest ? 'book-chip best' : 'book-chip'} title={`${p.bookName} · ${relTime(p.updatedAt)}`}>
              <span className="book-abbr">{p.bookName.slice(0, 2).toUpperCase()}</span>
              {fmtAmerican(p.price)}
            </span>
          ))}
        </div>
      </td>
      <td className="cell-move">
        {canSeeMovement ? <Sparkline points={o.movement} /> : <LockChip required="pro" />}
      </td>
    </tr>
  )
}

export function EvScreen() {
  const { data, loading, error } = useAsync(fetchEvScreen, [])
  const [market, setMarket] = useState<MarketType>('h2h')
  const [onlyEv, setOnlyEv] = useState(false)

  const rows = useMemo(() => {
    if (!data) return []
    const out: { event: EventRow; outcome: Outcome }[] = []
    for (const ev of data.events) {
      const m = ev.markets.find((mk) => mk.type === market)
      if (!m) continue
      for (const o of m.outcomes) {
        const plusEv = o.isPlusEv ?? o.ev > 0
        if (onlyEv && !plusEv) continue
        out.push({ event: ev, outcome: o })
      }
    }
    return out.sort((a, b) => b.outcome.ev - a.outcome.ev)
  }, [data, market, onlyEv])

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>EV &amp; Line Shopping</h1>
          <p className="lede">
            Best available price per market across books, with +EV flagged
            against no-vig fair value. Numbers are estimates of expected value,
            not guarantees.
          </p>
        </div>
        {data && <div className="freshness">Updated {relTime(data.generatedAt)}</div>}
      </div>

      <div className="toolbar">
        <div className="tabs">
          {MARKET_TABS.map((t) => (
            <button key={t.key} className={t.key === market ? 'tab active' : 'tab'} onClick={() => setMarket(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={onlyEv} onChange={(e) => setOnlyEv(e.target.checked)} />
          +EV only
        </label>
      </div>

      {loading && <div className="state">Loading odds…</div>}
      {error && <div className="state state-error">Couldn’t load odds: {error}</div>}

      {data && !loading && (
        <div className="table-wrap">
          <table className="ev-table">
            <thead>
              <tr>
                <th>Selection</th>
                <th>Fair</th>
                <th>Best price</th>
                <th>EV</th>
                <th>All books</th>
                <th>Movement</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ event, outcome }) => (
                <OutcomeRow key={`${event.id}-${outcome.name}`} o={outcome} event={event} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="state">No selections match this filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <p className="disclaimer">
        Fair value uses a no-vig model from our quant methodology. Lines move —
        the price you actually get may differ. Bet responsibly.
      </p>
      {data && (
        <p className="muted next-game">
          Next event: {fmtTime(data.events[0]?.startTime ?? '')}
        </p>
      )}
    </section>
  )
}
