import type { Tier } from './types'

// ---------------------------------------------------------------------------
// Central app config. Pricing, payment links, and compliance copy live here
// (not hard-coded in components) so they're easy to update without touching UI.
// Pricing confirmed by lead: Pro $49/mo, Elite $179/mo (annual-equiv $39/$149).
// ---------------------------------------------------------------------------

export interface PlanConfig {
  tier: Tier
  name: string
  monthly: number
  annualEquiv: number | null
  pitch: string
  blurb: string
  features: string[]
  cta: string
  /** Hosted payment link from the lead's managed Stripe. Empty until provided. */
  paymentLinkMonthly: string
  paymentLinkAnnual: string
}

export const PLANS: PlanConfig[] = [
  {
    tier: 'free',
    name: 'Free',
    monthly: 0,
    annualEquiv: null,
    pitch: 'See the edge exists.',
    blurb: 'A genuinely useful, genuinely honest taste of the market.',
    features: [
      'Daily odds snapshot (delayed)',
      'Top 3 +EV plays daily',
      'Line shopping — 1 sport, top books',
      'Public CLV track record',
    ],
    cta: 'Start free',
    paymentLinkMonthly: '',
    paymentLinkAnnual: '',
  },
  {
    tier: 'pro',
    name: 'Pro',
    monthly: 49,
    annualEquiv: 39,
    pitch: 'Find and shop every edge, in real time.',
    blurb: 'Real-time line shopping, the full +EV feed, and line movement.',
    features: [
      'Real-time odds, all major books',
      'Full +EV screen across all markets',
      'Line movement: steam, RLM, open→close',
      'Personal CLV dashboard',
      'Historical odds database',
      'Opt-in EV & movement alerts',
    ],
    cta: 'Upgrade to Pro',
    paymentLinkMonthly: '', // TODO: lead to provide hosted payment link
    paymentLinkAnnual: '',
  },
  {
    tier: 'elite',
    name: 'Elite',
    monthly: 179,
    annualEquiv: 149,
    pitch: 'Run it like a pro.',
    blurb: 'Everything in Pro, plus the tools to act on edges at scale.',
    features: [
      'Everything in Pro',
      'Arbitrage & middling finders',
      'Kelly sizing & bankroll tooling',
      'Advanced models & custom dashboards',
      'API / data feed access',
      'Custom-criteria priority alerts',
    ],
    cta: 'Go Elite',
    paymentLinkMonthly: '', // TODO: lead to provide hosted payment link
    paymentLinkAnnual: '',
  },
]

// Compliance copy — load-bearing, rendered on every page. Do not soften.
export const COMPLIANCE = {
  ageGeo: '21+ (or legal age in your jurisdiction). Available in regulated markets only.',
  helpline: '1-800-GAMBLER',
  helplineUrl: 'https://www.ncpgambling.org/',
  notBets:
    'EdgeWire provides information and analytics only. We do not accept wagers, hold funds, or guarantee outcomes.',
  evFraming:
    'Everything here is probability and expected value — not a promise of profit. No tool can guarantee a win.',
  affiliate:
    'Some sportsbook links may be affiliate links: EdgeWire may earn a commission if you sign up, at no cost to you. This never affects which prices or edges we show.',
}
