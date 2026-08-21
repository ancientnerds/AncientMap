/**
 * Closing block on every indexed page: the globe and the Discord.
 *
 * Originally mirrored community_cta_html() in the Python renderer; since
 * react-ssr Task 16 this component is the only definition — server and
 * browser render it from the same tree. (The old split is why the site
 * detail page's globe button vanished on mount, audit 2026-08-09.)
 */

import { discordCtaUrl } from '../../constants/brand'

const HUBS: [string, string][] = [
  ['/globe.html', '3D Globe'],
  ['/sites/', 'Sites by country'],
  ['/news-archive/', 'Story Archive'],
  ['/research/', 'Research Library'],
  ['/articles/', 'Weekly Journal'],
  ['/search.html', 'Search'],
]

interface CommunityCtaProps {
  /**
   * Where the globe button points. The site detail page passes its own
   * focused URL so the page has ONE globe button instead of two that lead
   * to different places (its own plus the generic one down here).
   */
  globeHref?: string
  globeLabel?: string
}

export default function CommunityCta({
  globeHref = '/globe.html',
  globeLabel = 'Open the 3D globe',
}: CommunityCtaProps = {}) {
  return (
    <div className="community-cta">
      <h2>Keep exploring</h2>
      <p>
        Every site on this page sits on the globe, and the people who research
        them are on the Discord.
      </p>
      {/* Two equal NERV action buttons. The globe used to be a rounded red
          pill and Discord only an inline link inside a sentence — two styles
          on the one block that appears on all nine indexed page types. */}
      <div className="community-cta-actions">
        <a className="community-cta-btn" href={globeHref}>
          {globeLabel}
        </a>
        <a
          className="community-cta-btn"
          href={discordCtaUrl('seo')}
          target="_blank"
          rel="noopener noreferrer"
        >
          Join the Discord
        </a>
      </div>
      {/* HamburgerNav renders its items only after a click
          (`{open && (`, HamburgerNav.tsx:96), so a crawler sees no navigation
          at all. These are the only crawlable links between the hubs. */}
      <p className="community-cta-hubs">
        {HUBS.map(([href, label], i) => (
          <span key={href}>
            {i > 0 && ' · '}
            <a href={href}>{label}</a>
          </span>
        ))}
      </p>
    </div>
  )
}
