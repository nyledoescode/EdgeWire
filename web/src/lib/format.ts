// Display formatters for odds / EV / probabilities.

export function fmtAmerican(odds: number): string {
  if (!Number.isFinite(odds) || odds === 0) return '—'
  return odds > 0 ? `+${odds}` : `${odds}`
}

export function fmtEv(ev: number): string {
  const pct = ev * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

export function fmtPct(p: number, digits = 0): string {
  return `${(p * 100).toFixed(digits)}%`
}

export function fmtClv(pp: number): string {
  const sign = pp >= 0 ? '+' : ''
  return `${sign}${pp.toFixed(2)}pp`
}

/** Fair-value probability delta in percentage points (Spec 03 movement). */
export function fmtProbDeltaPp(pp: number): string {
  const sign = pp >= 0 ? '+' : ''
  return `${sign}${pp.toFixed(1)} pts`
}

export function fmtTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.round(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
