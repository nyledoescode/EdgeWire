import { useState } from 'react'
import { useTier } from '../auth/TierContext'
import { PLANS, COMPLIANCE, type PlanConfig } from '../config'

function CtaButton({ plan, annual }: { plan: PlanConfig; annual: boolean }) {
  const { tier, has } = useTier()

  if (plan.tier === 'free') {
    return <button className="btn" disabled>{tier === 'free' ? 'Current plan' : 'Included'}</button>
  }
  if (has(plan.tier)) {
    return <button className="btn" disabled>Current plan</button>
  }
  const link = annual ? plan.paymentLinkAnnual : plan.paymentLinkMonthly
  if (!link) {
    // No Stripe call here — buttons route to hosted payment links from the lead.
    return (
      <button className="btn btn-primary" disabled title="Hosted payment link pending from lead">
        {plan.cta} (link pending)
      </button>
    )
  }
  return (
    <a className="btn btn-primary" href={link} target="_blank" rel="noreferrer">
      {plan.cta}
    </a>
  )
}

export function Pricing() {
  const [annual, setAnnual] = useState(false)

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Plans</h1>
          <p className="lede">
            Tools and data to find an edge — never picks or guarantees. Cancel
            anytime. Available in regulated markets, {COMPLIANCE.ageGeo}
          </p>
        </div>
      </div>

      <div className="billing-toggle">
        <button className={!annual ? 'active' : ''} onClick={() => setAnnual(false)}>Monthly</button>
        <button className={annual ? 'active' : ''} onClick={() => setAnnual(true)}>
          Annual <span className="save-tag">save</span>
        </button>
      </div>

      <div className="plans">
        {PLANS.map((plan) => {
          const price = plan.monthly === 0
            ? '$0'
            : `$${annual && plan.annualEquiv ? plan.annualEquiv : plan.monthly}`
          const cadence = plan.monthly === 0 ? 'forever' : '/mo'
          return (
            <div key={plan.tier} className={`plan plan-${plan.tier}`}>
              {plan.tier === 'pro' && <div className="plan-flag">Most popular</div>}
              <h2>{plan.name}</h2>
              <p className="plan-pitch">{plan.pitch}</p>
              <div className="plan-price">
                <span className="plan-amount">{price}</span>
                <span className="plan-cadence">{cadence}</span>
              </div>
              {annual && plan.annualEquiv && (
                <div className="plan-annual-note">billed annually · effective rate</div>
              )}
              <p className="plan-blurb">{plan.blurb}</p>
              <ul className="plan-features">
                {plan.features.map((f) => <li key={f}>{f}</li>)}
              </ul>
              <CtaButton plan={plan} annual={annual} />
            </div>
          )
        })}
      </div>

      <p className="disclaimer">
        {COMPLIANCE.notBets} {COMPLIANCE.evFraming} If gambling stops being fun,
        call {COMPLIANCE.helpline}. {COMPLIANCE.affiliate}
      </p>
    </section>
  )
}
