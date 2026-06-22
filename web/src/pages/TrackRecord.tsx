import { fetchClvSummary } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { fmtAmerican, fmtClv, fmtPct, fmtTime } from '../lib/format'
import type { ClvRecord, ClvSummary } from '../types'

function ResultPill({ r }: { r: ClvRecord['result'] }) {
  return <span className={`result-pill r-${r}`}>{r}</span>
}

const GATE_COPY: Record<NonNullable<ClvSummary['displayGate']>, { label: string; note: string; cls: string }> = {
  building: {
    label: 'Building sample',
    note: 'Too few graded plays to report a meaningful rate yet. We show every play as it settles rather than headline a number we can’t stand behind.',
    cls: 'gate-building',
  },
  small_sample: {
    label: 'Preliminary — small sample',
    note: 'Fewer than 30 graded plays. These rates are early indicators with wide confidence intervals, not a track record yet. We show them honestly rather than wait and cherry-pick.',
    cls: 'gate-small',
  },
  full: {
    label: 'Sufficient sample',
    note: 'Enough graded plays to present the rate with its confidence interval.',
    cls: 'gate-full',
  },
  verified: {
    label: 'Verified sample',
    note: 'Large, independently-auditable sample.',
    cls: 'gate-verified',
  },
}

function ci(pair?: [number, number], fmt?: (n: number) => string): string | null {
  if (!pair) return null
  const f = fmt ?? ((n: number) => `${n}`)
  return `95% CI ${f(pair[0])}–${f(pair[1])}`
}

export function TrackRecord() {
  const { data, loading, error } = useAsync(fetchClvSummary, [])
  const gate = data?.displayGate
  // Per Spec 02 §3.3: never headline a sub-30 sample. Suppress the big rate
  // when the gate says the sample isn't ready, but still show the full table.
  const headlineRates = gate === 'full' || gate === 'verified' || gate === undefined

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Track Record &amp; CLV</h1>
          <p className="lede">
            Closing Line Value is the honest measure of whether our flagged edges
            actually beat the market. We publish the full graded sample — wins,
            losses, and pushes — with sample size and confidence intervals, not a
            curated highlight reel.
          </p>
        </div>
      </div>

      <div className="trust-note">
        <strong>Why CLV, not win rate?</strong> Beating the closing line is the
        most reliable evidence that a process finds real value over time. Short-run
        win rate is mostly variance. We track CLV so you can audit us — and so we
        can’t hide behind cherry-picked records.
      </div>

      {loading && <div className="state">Loading track record…</div>}
      {error && <div className="state state-error">Couldn’t load: {error}</div>}

      {data && (
        <>
          {gate && GATE_COPY[gate] && (
            <div className={`gate-banner ${GATE_COPY[gate].cls}`} role="note">
              <span className="gate-label">{GATE_COPY[gate].label} · n = {data.sampleSize}</span>
              <span className="gate-note">{GATE_COPY[gate].note}</span>
            </div>
          )}

          <div className="stat-cards">
            <div className="stat-card">
              <div className={headlineRates ? 'stat-value' : 'stat-value stat-muted'}>
                {fmtPct(data.beatRate, 1)}
              </div>
              <div className="stat-label">Beat the close</div>
              {ci(data.beatRateCI95, (n) => fmtPct(n, 0)) && (
                <div className="stat-ci">{ci(data.beatRateCI95, (n) => fmtPct(n, 0))}</div>
              )}
            </div>
            <div className="stat-card">
              <div className={headlineRates ? 'stat-value' : 'stat-value stat-muted'}>
                {fmtClv(data.avgClvPct)}
              </div>
              <div className="stat-label">Average CLV</div>
              {ci(data.avgClvPctCI95, (n) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}pp`) && (
                <div className="stat-ci">{ci(data.avgClvPctCI95, (n) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}pp`)}</div>
              )}
            </div>
            <div className="stat-card">
              <div className="stat-value">{data.sampleSize}</div>
              <div className="stat-label">Graded plays</div>
            </div>
            <div className="stat-card">
              <div className="stat-value stat-window">{data.window}</div>
              <div className="stat-label">Sample window</div>
            </div>
          </div>

          <div className="table-wrap">
            <table className="clv-table">
              <thead>
                <tr>
                  <th>Placed</th>
                  <th>Event</th>
                  <th>Selection</th>
                  <th>Taken</th>
                  <th>Close</th>
                  <th>CLV</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {data.records.map((rec) => (
                  <tr key={rec.id}>
                    <td className="muted">{fmtTime(rec.placedAt)}</td>
                    <td>
                      <div>{rec.event}</div>
                      <div className="muted">{rec.sport} · {rec.market}</div>
                    </td>
                    <td>{rec.selection}</td>
                    <td>{fmtAmerican(rec.takenPrice)}</td>
                    <td>{fmtAmerican(rec.closingPrice)}</td>
                    <td className={rec.clvPct >= 0 ? 'clv-pos' : 'clv-neg'}>{fmtClv(rec.clvPct)}</td>
                    <td><ResultPill r={rec.result} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="disclaimer">
            Past CLV does not guarantee future results. This sample is illustrative
            mock data in the current preview; the live page will publish the real,
            independently-auditable record. Bet responsibly — 21+, regulated
            markets only.
          </p>
        </>
      )}
    </section>
  )
}
