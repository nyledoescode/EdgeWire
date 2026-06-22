import type { EvScreenResponse, ClvSummary, Capabilities } from '../types'
import { mockEvScreen, mockClvSummary } from './mockData'

// ---------------------------------------------------------------------------
// API client. Single swap point between mock data and the live backend.
//
// LIVE mode: set VITE_USE_API=true and point Vite's /api proxy at the backend
// (VITE_API_PROXY=http://127.0.0.1:8000). Each function targets the contracted
// endpoint; mappers below absorb the small backend/​frontend shape differences
// (snake_case capabilities, separate capabilities endpoint) so pages are
// unchanged whether data is mock or live.
// ---------------------------------------------------------------------------

const USE_API = import.meta.env.VITE_USE_API === 'true'

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json() as Promise<T>
}

// Simulate latency so loading states are exercised in mock mode.
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

// Backend /api/capabilities is snake_case and a separate endpoint; map it to
// the frontend Capabilities shape. Defensive defaults keep the UI honest if a
// field is missing (assume no splits, proxy mode — never fabricate).
function mapCapabilities(raw: Record<string, unknown> | null | undefined): Capabilities {
  return {
    splitsAvailable: Boolean(raw?.['splits_available']),
    sharpCoverage: (raw?.['sharp_coverage'] as Capabilities['sharpCoverage']) ?? 'none',
    rlmMode: (raw?.['rlm_mode'] as Capabilities['rlmMode']) ?? 'sharp_proxy',
    steamFidelity: (raw?.['steam_fidelity'] as Capabilities['steamFidelity']) ?? 'coarse',
  }
}

const DEFAULT_CAPS: Capabilities = {
  splitsAvailable: false,
  sharpCoverage: 'none',
  rlmMode: 'sharp_proxy',
  steamFidelity: 'coarse',
}

export async function fetchEvScreen(): Promise<EvScreenResponse> {
  if (!USE_API) {
    await delay(250)
    return mockEvScreen
  }
  // The live backend exposes capabilities on a separate endpoint and may not
  // embed it in ev-screen; fetch both and merge so the UI's degradation logic
  // (Sharp-Move proxy, etc.) works identically to mock mode.
  const [screen, caps] = await Promise.all([
    getJSON<EvScreenResponse>('/api/ev-screen'),
    getJSON<Record<string, unknown>>('/api/capabilities').catch(() => null),
  ])
  return {
    ...screen,
    capabilities: screen.capabilities ?? (caps ? mapCapabilities(caps) : DEFAULT_CAPS),
  }
}

export async function fetchClvSummary(): Promise<ClvSummary> {
  if (USE_API) return getJSON<ClvSummary>('/api/clv-summary')
  await delay(250)
  return mockClvSummary
}
