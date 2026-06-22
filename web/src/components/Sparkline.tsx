import type { MovementPoint } from '../types'

// Lightweight inline SVG sparkline for line movement. No chart library —
// keeps the bundle (and memory) small.
//
// Per Spec 03 §0, movement is plotted in NO-VIG CONSENSUS PROBABILITY space
// when available (`consensusFairProb`), falling back to price only if the prob
// series is absent. Plotting prob is the honest signal — a lengthening price
// can hide a fair value that moved against the side.
export function Sparkline({
  points,
  width = 84,
  height = 24,
}: {
  points: MovementPoint[]
  width?: number
  height?: number
}) {
  if (!points || points.length < 2) {
    return <span className="spark-empty" title="No movement data">—</span>
  }
  // Prefer the consensus no-vig probability series; fall back to price.
  const useProb = points.every((p) => p.consensusFairProb != null)
  const series = points.map((p) =>
    useProb ? (p.consensusFairProb as number) : p.price,
  )
  const min = Math.min(...series)
  const max = Math.max(...series)
  const span = max - min || 1
  const stepX = width / (points.length - 1)

  const coords = points.map((_, i) => {
    const x = i * stepX
    // Draw UP when the value increased (higher prob = more likely; or higher
    // american = better payout in the price-fallback case).
    const y = height - ((series[i] - min) / span) * (height - 4) - 2
    return [x, y] as const
  })
  const d = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')

  const first = series[0]
  const last = series[series.length - 1]
  const up = last >= first
  const stroke = up ? 'var(--good)' : 'var(--bad)'
  const [lx, ly] = coords[coords.length - 1]

  return (
    <svg
      className="spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Fair-value movement ${up ? 'up' : 'down'}`}
    >
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r="2" fill={stroke} />
    </svg>
  )
}

