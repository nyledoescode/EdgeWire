import { COMPLIANCE } from '../config'

// Load-bearing compliance furniture. Rendered on every page (not just footer)
// per growth's responsible-gambling requirements. Do not remove or soften.
export function ResponsibleGamblingBand() {
  return (
    <div className="rg-band" role="note">
      <span className="rg-icon" aria-hidden="true">🔞</span>
      <span>
        <strong>Bet smart. Bet within your means.</strong> {COMPLIANCE.notBets}{' '}
        {COMPLIANCE.evFraming} Must be {COMPLIANCE.ageGeo} If gambling stops being
        fun, help is available:{' '}
        <a href={COMPLIANCE.helplineUrl} target="_blank" rel="noreferrer">
          {COMPLIANCE.helpline}
        </a>
        .
      </span>
    </div>
  )
}
