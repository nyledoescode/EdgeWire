import { Link } from 'react-router-dom'
import type { Tier } from '../types'

const LABEL: Record<Tier, string> = { free: 'Free', pro: 'Pro', elite: 'Elite' }

// Shown in place of (or over) gated content. Routes users to /pricing, which is
// where hosted-payment-link Buy buttons live. No Stripe logic here.
export function PaywallCard({
  required,
  feature,
}: {
  required: Tier
  feature: string
}) {
  return (
    <div className="paywall">
      <div className="paywall-badge">{LABEL[required]}</div>
      <h3>{feature} is a {LABEL[required]} feature</h3>
      <p>
        Upgrade to unlock {feature.toLowerCase()}. EdgeWire is an analytics tool —
        every insight is framed as expected value and probability, never a
        guaranteed outcome.
      </p>
      <Link className="btn btn-primary" to="/pricing">
        See plans
      </Link>
    </div>
  )
}

// Inline lock chip for individual locked cells/rows.
export function LockChip({ required }: { required: Tier }) {
  return (
    <Link to="/pricing" className="lock-chip" title={`${LABEL[required]} feature`}>
      🔒 {LABEL[required]}
    </Link>
  )
}
