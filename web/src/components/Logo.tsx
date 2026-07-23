/**
 * BestBet brand mark — a crisp, ownable SVG logo.
 *
 * Concept: a rising "edge" — three ascending bars forming an upward line-movement
 * motif, cut by a sharp diagonal signal line that reads as the market edge being
 * caught. Geometric, precise, terminal-like. Uses the brand emerald→cyan gradient.
 *
 * Delivered as inline SVG (no raster) so it's razor-sharp at any size and adds
 * ~1KB to the bundle. `size` controls the mark; the wordmark is optional.
 */
export function LogoMark({ size = 26, title = 'BestBet' }: { size?: number; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label={title}
      className="logo-mark"
    >
      <defs>
        <linearGradient id="ew-grad" x1="4" y1="28" x2="28" y2="4" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3ddc97" />
          <stop offset="1" stopColor="#2bb3ff" />
        </linearGradient>
      </defs>
      {/* ascending edge bars */}
      <rect x="4" y="19" width="4.5" height="9" rx="1.4" fill="url(#ew-grad)" opacity="0.55" />
      <rect x="13.75" y="13" width="4.5" height="15" rx="1.4" fill="url(#ew-grad)" opacity="0.78" />
      <rect x="23.5" y="6" width="4.5" height="22" rx="1.4" fill="url(#ew-grad)" />
      {/* sharp signal line catching the edge */}
      <path
        d="M4 20 L15.5 12 L27 4"
        stroke="#e6ebf5"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.92"
      />
      {/* signal node */}
      <circle cx="27" cy="4" r="2.6" fill="#e6ebf5" />
      <circle cx="27" cy="4" r="2.6" fill="url(#ew-grad)" opacity="0.35" />
    </svg>
  )
}

export function Logo() {
  return (
    <span className="brand-lockup">
      <LogoMark size={26} />
      <span className="brand-wordmark">
        <span className="brand-name">BestBet</span>
        <span className="brand-tag">Odds Intelligence</span>
      </span>
    </span>
  )
}
