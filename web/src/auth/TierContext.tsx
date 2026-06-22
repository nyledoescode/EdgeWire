import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Tier } from '../types'

// ---------------------------------------------------------------------------
// Tier / "auth" context. For the mock build this is a simple client-side flag
// so we can demo Free / Pro / Elite gating. When real auth lands, replace the
// initial value with the tier read from the session/JWT and keep the same API.
//
// NOTE: client-side gating is for UX only. The backend MUST enforce tier on the
// data it returns. This never holds Stripe keys or calls Stripe directly —
// checkout uses hosted payment links provided by the lead.
// ---------------------------------------------------------------------------

const TIER_RANK: Record<Tier, number> = { free: 0, pro: 1, elite: 2 }

interface TierContextValue {
  tier: Tier
  setTier: (t: Tier) => void
  /** True if current tier meets or exceeds the required tier. */
  has: (required: Tier) => boolean
}

const TierContext = createContext<TierContextValue | null>(null)

export function TierProvider({ children }: { children: ReactNode }) {
  const [tier, setTier] = useState<Tier>('free')
  const value = useMemo<TierContextValue>(
    () => ({
      tier,
      setTier,
      has: (required) => TIER_RANK[tier] >= TIER_RANK[required],
    }),
    [tier],
  )
  return <TierContext.Provider value={value}>{children}</TierContext.Provider>
}

export function useTier() {
  const ctx = useContext(TierContext)
  if (!ctx) throw new Error('useTier must be used within TierProvider')
  return ctx
}
