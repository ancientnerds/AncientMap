/**
 * SiteCard — Reusable archaeological site card component.
 *
 * Pure display component. Can be used anywhere:
 * - Search page grid
 * - Hover tooltips over site mentions in text
 * - News feed site references
 * - Lyra chat site results
 *
 * The consumer controls what happens on click and what actions appear
 * via the optional `actions` render prop.
 */

import LazyImage from './LazyImage'
import { SiteBadges, CountryFlag, CopyButton } from './metadata'
import { FitText } from './FitText'
import { extractCountry } from '../utils/searchUtils'
import { formatCoord } from '../utils/formatters'
import { globeUrlForSite } from '../constants/brand'
import { getSourceColor } from '../data/sites'
import type { SiteData } from '../data/sites'
import './site-card.css'

export interface SiteCardProps {
  site: SiteData
  /** Source display name (resolved from sourceId if not provided) */
  sourceName?: string
  /** Source color (resolved from sourceId if not provided) */
  sourceColor?: string
  /** Click handler for the entire card */
  onClick?: () => void
  /** Optional render prop for footer actions (e.g., "View on Globe" link) */
  actions?: React.ReactNode
  /** Compact mode — no description, no footer. For hover tooltips. */
  compact?: boolean
}

export function SiteCard({ site, sourceName, sourceColor, onClick, actions, compact }: SiteCardProps) {
  const country = extractCountry(site.location)
  const [lng, lat] = site.coordinates
  const hasCoords = !isNaN(lat) && !isNaN(lng) && (lat !== 0 || lng !== 0)
  const resolvedColor = sourceColor || getSourceColor(site.sourceId)
  const coordsText = hasCoords ? `${formatCoord(lat, true)}, ${formatCoord(lng, false)}` : ''

  return (
    <div
      className={`site-card${compact ? ' site-card--compact' : ''}`}
      // Machine-readable only (design: no visual change on cards); the visible notice is
      // on the site's page, which the card opens.
      data-description-ai={site.descriptionAi}
      data-card-ai={site.cardAi}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? e => { if (e.key === 'Enter') onClick() } : undefined}
    >
      {site.image && (
        <div className="site-card-hero">
          <div className="site-card-hero-shimmer" />
          <LazyImage src={site.image} alt={site.title} overlay className="site-card-hero-img" />
          <div className="site-card-vignette" />
          <div className="site-card-title-row">
            <h3 className="site-card-title">{site.title}</h3>
            {!compact && <CopyButton text={site.title} title="Copy name" size={11} />}
          </div>
        </div>
      )}

      <div className="site-card-body">
        {!site.image && (
          <div className="site-card-title-row">
            <h3 className="site-card-title-plain">{site.title}</h3>
            {!compact && <CopyButton text={site.title} title="Copy name" size={11} />}
          </div>
        )}

        <div className="site-card-location">
          {country !== 'Unknown' && (
            <span className="site-card-country">
              <CountryFlag country={country} size="sm" />
              <span>{country}</span>
            </span>
          )}
          {hasCoords && (
            <span className="site-card-coords">
              <svg className="site-card-coords-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="2" y1="12" x2="22" y2="12"></line>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
              </svg>
              {coordsText}
              {!compact && <CopyButton text={coordsText} title="Copy coordinates" size={10} />}
            </span>
          )}
        </div>

        <SiteBadges
          category={site.category}
          period={site.period}
          periodStart={site.periodStart}
          size="sm"
          hideExactYear
        />

        {!compact && site.cardDescription && (
          <FitText
            text={site.cardDescription}
            maxPx={11}
            lines={4}
            className="site-card-desc"
          />
        )}
        {!compact && !site.cardDescription && site.description && (
          <p className="site-card-desc site-card-desc--wiki">{site.description}</p>
        )}

        {!compact && (actions || sourceName) && (
          <div className="site-card-footer">
            {sourceName && (
              <span className="site-card-source" style={{ borderColor: resolvedColor, color: resolvedColor }}>
                {sourceName}
              </span>
            )}
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * ViewOnGlobeLink — "View on Globe" action for SiteCard footer.
 * Reuses an existing globe tab via postMessage, opens a new one if needed.
 */

let globeWindow: Window | null = null

/** Navigate to a site on the globe — reuses existing globe tab via postMessage. */
export function viewOnGlobe(siteId: string) {
  if (globeWindow && !globeWindow.closed) {
    globeWindow.postMessage({ type: 'focus-site', siteId }, window.location.origin)
    globeWindow.focus()
    return
  }
  globeWindow = window.open(`/globe.html?focus=${siteId}`, 'ancient-nerds-globe')
}

export function ViewOnGlobeLink({ siteId }: { siteId: string }) {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    viewOnGlobe(siteId)
  }

  return (
    <a
      href={globeUrlForSite(siteId)}
      className="site-card-globe-link"
      onClick={handleClick}
    >
      View on Globe
    </a>
  )
}
