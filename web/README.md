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

## Deploying to Vercel

The app deploys to Vercel as a **static Vite SPA**. Config lives in `web/vercel.json`.

**Vercel project settings** (Import → configure once):
- **Root Directory:** `web` (the app is a subfolder of the `nyledoescode/EdgeWire` monorepo)
- **Framework Preset:** Vite (auto-detected)
- **Build Command:** `npm run build`  (runs `tsc -b && vite build`)
- **Output Directory:** `dist`
- **Install Command:** `npm ci`
- **SPA rewrite:** handled by `vercel.json` — every non-`/api/` path rewrites to
  `/index.html` so client-side routes (`/ev`, `/movement`, `/track-record`,
  `/pricing`) resolve on hard-refresh / deep link. `/api/*` is left untouched so
  a hosted API can be added later without a config change.

**Environment variables:**
- **Leave `VITE_USE_API` UNSET (or `false`) in the Vercel build.** The public
  deploy runs on illustrative mock fixtures (`src/api/mockData.ts`) so the full
  product renders with no backend dependency. Vite statically folds the unset
  flag to the mock path at build time (the string `VITE_USE_API` doesn't even
  appear in the bundle).
- Only set `VITE_USE_API=true` + `VITE_API_PROXY=<api-origin>` **after** the
  intelligence API is separately hosted and reachable from the browser. Until
  then, keep it unset — a live flag with no reachable API would render an
  error state on the public URL.

Deploy is a one-shot once the token is set: `vercel --prod` from `web/` (or
connect the Git repo with Root Directory `web` for push-to-deploy).

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
Mock-data build, **Vercel deploy-ready** (`vercel.json` + verified clean static
`dist`, SPA rewrite tested). All data is illustrative, not live odds or advice.
Still needs: hosted payment links from the lead, and (later) a separately-hosted
live backend API before flipping `VITE_USE_API=true`.
