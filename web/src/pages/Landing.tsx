import { Link } from 'react-router-dom'
import { PLANS, COMPLIANCE } from '../config'

const FEATURES = [
  { icon: '🛒', title: 'Line shopping', line: 'Best available price on every market, across every book. Never leave value on the table.' },
  { icon: '🎯', title: '+EV screen', line: 'Real-time detection of mispriced lines vs. fair value, ranked by edge.' },
  { icon: '📈', title: 'Line movement', line: 'Steam moves, reverse line movement, open→close tracking, sharp vs. public signals.' },
  { icon: '🧾', title: 'CLV tracking', line: 'Did you beat the close? Track your edge with the metric the pros trust.' },
]

const PROBLEM = [
  '"Guaranteed locks" and made-up win rates you can\u2019t verify',
  'Urgency and hype designed to make you click, not sharper',
  'No idea why a bet was recommended',
]
const PROMISE = [
  'Every edge quantified as +EV, with no-vig fair value shown',
  'Auditable CLV track record — proof, not promises',
  'The reasoning, always — we teach you to read the market',
]

export function Landing() {
  return (
    <section className="landing">
      {/* Hero */}
      <div className="hero">
        <h1 className="hero-h1">Stop betting blind. See the edge — in real time.</h1>
        <p className="hero-sub">
          EdgeWire monitors every major sportsbook and surfaces +EV opportunities,
          line movement, and the best available price the moment it appears.
          Intelligence, not “guaranteed picks.”
        </p>
        <div className="hero-cta">
          <Link className="btn btn-primary btn-lg" to="/pricing">Start free</Link>
          <Link className="btn btn-lg" to="/ev">See how it works</Link>
        </div>
        <p className="hero-micro">Free to start · {COMPLIANCE.ageGeo}</p>
      </div>

      {/* Trust bar */}
      <div className="trust-bar">
        <strong>We don’t sell picks. We sell the edge — and we prove it.</strong>
        <span>
          Every signal is shown as expected value with the math behind it. And we
          track our Closing Line Value publicly — the one measure of edge you
          can’t fake.
        </span>
      </div>

      {/* Problem -> Promise */}
      <div className="pp-grid">
        <div className="pp-card pp-problem">
          <h3>The problem with most betting “advice”</h3>
          <ul>{PROBLEM.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
        <div className="pp-card pp-promise">
          <h3>The EdgeWire way</h3>
          <ul>{PROMISE.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      </div>

      {/* Features */}
      <div className="feature-grid">
        {FEATURES.map((f) => (
          <div key={f.title} className="feature-card">
            <div className="feature-icon">{f.icon}</div>
            <h4>{f.title}</h4>
            <p>{f.line}</p>
          </div>
        ))}
      </div>
      <p className="feature-note">
        Elite adds: arbitrage &amp; middling finders, Kelly sizing, historical
        models, and API access.
      </p>

      {/* CLV trust section */}
      <div className="clv-trust">
        <h2>Why we lead with Closing Line Value</h2>
        <p>
          A “win rate” can be cherry-picked or invented. Closing Line Value can’t —
          the closing line is public, and beating it consistently is the most
          respected proxy for a real, long-term edge. We track the CLV of the edges
          we flag, openly. It’s our receipt.
        </p>
        <Link className="btn" to="/track-record">See our track record</Link>
      </div>

      {/* Pricing teaser */}
      <div className="pricing-teaser">
        {PLANS.map((p) => (
          <div key={p.tier} className={`teaser teaser-${p.tier}`}>
            <h4>{p.name}</h4>
            <div className="teaser-price">
              {p.monthly === 0 ? '$0' : `$${p.monthly}`}
              {p.monthly !== 0 && <span>/mo</span>}
            </div>
            <p className="teaser-pitch">{p.pitch}</p>
          </div>
        ))}
      </div>
      <div className="landing-cta">
        <Link className="btn btn-primary btn-lg" to="/pricing">See full plans</Link>
        <p className="muted">No card required for Free.</p>
      </div>
    </section>
  )
}
