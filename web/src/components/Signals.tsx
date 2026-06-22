import type { MovementSignal, Capabilities } from '../types'
import { relTime } from '../lib/format'

const SIGNAL_META: Record<MovementSignal['type'], { icon: string; label: string; cls: string }> = {
  steam: { icon: '🔥', label: 'Steam', cls: 'sig-steam' },
  sharp_move: { icon: '🎯', label: 'Sharp move', cls: 'sig-sharp' },
  rlm: { icon: '↩️', label: 'RLM', cls: 'sig-rlm' },
}

function SignalChip({ s }: { s: MovementSignal }) {
  const meta = SIGNAL_META[s.type]
  const arrow = s.direction === 'toward' ? '→' : '⤺'
  return (
    <span className={`sig-chip ${meta.cls}`} title={`${meta.label} • ${s.nBooksMoved}/${s.booksTotal} books • ${relTime(s.detectedAt)}`}>
      <span className="sig-icon">{meta.icon}</span>
      <span className="sig-label">{meta.label}</span>
      <span className="sig-detail">
        {arrow} {s.selection} · {s.magnitudePp.toFixed(1)} pts fair · {s.nBooksMoved}/{s.booksTotal} books
        {s.sharpLed ? ' · sharp-led' : ''}
      </span>
    </span>
  )
}

export function SignalsStrip({ signals }: { signals?: MovementSignal[] }) {
  if (!signals || signals.length === 0) return null
  return (
    <div className="signals-strip">
      {signals.map((s, i) => (
        <SignalChip key={`${s.type}-${s.selection}-${i}`} s={s} />
      ))}
      <span className="signals-note">Market context, not a signal to chase.</span>
    </div>
  )
}

/**
 * Graceful-degradation note for RLM (Spec 03 §3.5). When we have no betting
 * splits feed, we show the labeled Sharp-Move proxy and say so honestly — we
 * NEVER fabricate public ticket/handle percentages.
 */
export function RlmModeNote({ caps }: { caps: Capabilities }) {
  if (caps.rlmMode === 'true_rlm') return null
  return (
    <div className="rlm-note" role="note">
      <strong>Showing sharp-vs-soft line leadership, not public splits.</strong>{' '}
      Ticket/handle betting splits aren’t in our current data tier, so we don’t
      report public bet percentages or true Reverse Line Movement — we never
      fabricate those. Instead we surface where the sharp/low-vig books moved
      first and the soft market is following (an honest, price-only proxy).
    </div>
  )
}
