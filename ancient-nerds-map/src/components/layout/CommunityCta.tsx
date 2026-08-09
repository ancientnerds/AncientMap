/**
 * Closing block on every indexed page: the globe and the Discord.
 *
 * Mirrors community_cta_html() in pipeline/seo_pages.py. It has to exist in
 * both worlds — the server fragment alone would vanish the instant React
 * replaced #root, which is exactly what happened to the site detail page's
 * globe button (audit 2026-08-09).
 */

import { DISCORD_INVITE_URL } from '../../constants/brand'

export default function CommunityCta() {
  return (
    <div className="community-cta">
      <h2>Keep exploring</h2>
      <p>
        <a className="community-cta-globe" href="/globe.html">
          Open the interactive 3D globe →
        </a>
      </p>
      <p>
        Questions, finds, corrections?{' '}
        <a href={DISCORD_INVITE_URL} target="_blank" rel="noopener noreferrer">
          Join the Ancient Nerds Discord
        </a>{' '}
        — the people behind these pages are there.
      </p>
    </div>
  )
}
