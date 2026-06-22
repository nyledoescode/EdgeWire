import { NavLink, Outlet, Link } from 'react-router-dom'
import { useTier } from '../auth/TierContext'
import { ResponsibleGamblingBand } from './ResponsibleGamblingBand'
import { COMPLIANCE } from '../config'
import type { Tier } from '../types'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/ev', label: 'EV Screen' },
  { to: '/movement', label: 'Line Movement' },
  { to: '/track-record', label: 'Track Record' },
  { to: '/pricing', label: 'Pricing' },
]

const TIERS: Tier[] = ['free', 'pro', 'elite']

export function Layout() {
  const { tier, setTier } = useTier()
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">⚡</span>
          <span className="brand-name">EdgeWire</span>
          <span className="brand-tag">Odds Intelligence</span>
        </Link>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="tier-switch" title="Demo only: simulate a subscription tier">
          <span className="tier-switch-label">View as</span>
          {TIERS.map((t) => (
            <button
              key={t}
              className={t === tier ? 'tier-pill active' : 'tier-pill'}
              onClick={() => setTier(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </header>

      <ResponsibleGamblingBand />

      <main className="content">
        <Outlet />
      </main>

      <footer className="footer">
        <div className="footer-grid">
          <div>
            <strong>EdgeWire</strong> is an odds-analytics and line-shopping tool.
            We surface expected value, line movement, and closing-line value from
            public sportsbook markets. We are <em>not</em> a tipster service and
            make <em>no</em> guaranteed-return claims. {COMPLIANCE.notBets}
          </div>
          <div className="footer-compliance">
            <p>
              <strong>{COMPLIANCE.ageGeo}</strong> Availability is geo-restricted;
              features may be limited by jurisdiction.
            </p>
            <p>
              If gambling stops being fun, get help. Call{' '}
              <a href={COMPLIANCE.helplineUrl} target="_blank" rel="noreferrer">
                {COMPLIANCE.helpline}
              </a>{' '}
              or visit ncpgambling.org. Please bet responsibly.
            </p>
            <p className="footer-affiliate">{COMPLIANCE.affiliate}</p>
          </div>
        </div>
        <div className="footer-fine">
          Odds and analytics shown in this preview are illustrative mock data, not
          live prices or betting advice.
        </div>
      </footer>
    </div>
  )
}
