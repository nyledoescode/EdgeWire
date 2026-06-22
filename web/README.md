# EdgeWire Web

Subscriber-facing web app for EdgeWire — odds intelligence & betting analytics
(line shopping, +EV screen, line movement, CLV track record). Vite + React + TS,
kept deliberately memory-light. **No Stripe keys / calls live here** — checkout
uses hosted payment links from the lead (wired in `src/config.ts`).

## Run it

```bash
npm install
npm run build      # tsc + vite build (do NOT run while dev server is up)
npm run serve      # vite preview on 0.0.0.0:3000  (the team's public surface)
```

Then open http://localhost:3000 . Dev mode (HMR): `npm run dev` (also binds :3000).

Background (survives shell exit):
```bash
nohup npm run serve > /tmp/edgewire-web.log 2>&1 &
```

## Pages
- `/` — landing (growth-approved copy, trust bar, pricing teaser)
- `/ev` — EV / line-shopping screen (core view): events × books, best price,
  +EV badges, all-books chips, line-movement sparkline (Pro-gated)
- `/movement` — line-movement detail (Pro-gated, paywall card for Free)
- `/track-record` — CLV / honest track record (the trust moat)
- `/pricing` — Free / Pro / Elite, monthly/annual toggle, hosted-payment-link CTAs

## Tier gating
Top-right "View as" switch simulates Free / Pro / Elite (demo only). Real auth
replaces the initial tier in `src/auth/TierContext.tsx`. **Client gating is UX
only — the backend MUST enforce tier on returned data.**

## Wiring to the real backend
Single swap point: `src/api/client.ts`.
1. Set `VITE_USE_API=true` (and `VITE_API_PROXY=http://127.0.0.1:8000` in the
   env so `/api` proxies to the backend).
2. Endpoints already targeted: `GET /api/ev-screen`, `GET /api/clv-summary`.
3. Response shapes are defined in `src/types.ts` and documented in
   `API_CONTRACT.md` — backend should match these (or send deltas).

## Config
`src/config.ts` holds pricing (Pro $49 / Elite $179; annual-equiv $39 / $149),
hosted payment-link placeholders, and the load-bearing compliance copy.
Update pricing/links there — not in components.

## Compliance furniture (do not remove)
- Responsible-gambling band on every page (`ResponsibleGamblingBand`) + 1-800-GAMBLER
- 21+ / regulated-markets-only notices; geo-gating language
- "info & analytics only — we don't take bets or guarantee outcomes"
- Affiliate-link disclosure in footer
- Everything framed as probability / EV — no guaranteed-return language, no
  countdowns / "risk-free" / "guaranteed" copy

## Status
Mock-data build. All data is illustrative, not live odds or advice. Needs:
a linked repo, the live backend API, and hosted payment links from the lead.
