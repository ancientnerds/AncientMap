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

import { useState } from 'react'
import LazyImage from './LazyImage'
import { SiteBadges, CountryFlag, CopyButton } from './metadata'
import { FitText } from './FitText'
import { extractCountry } from '../utils/searchUtils'
import { formatCoord } from '../utils/formatters'
import { shareOrCopy } from '../utils/share'
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
      href={`/globe.html?focus=${siteId}`}
      className="site-card-globe-link"
      onClick={handleClick}
    >
      View on Globe
    </a>
  )
}

/**
 * FullPageLink — Opens the dedicated site page.
 */
export function FullPageLink({ siteId }: { siteId: string }) {
  return (
    <a
      href={`/site.html?id=${siteId}`}
      className="site-card-action-link"
      onClick={e => e.stopPropagation()}
      title="Open full page"
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
        <polyline points="15 3 21 3 21 9" />
        <line x1="10" y1="14" x2="21" y2="3" />
      </svg>
      Full Page
    </a>
  )
}

/**
 * ShareSiteLink — Copies the OG share link (with preview image) to clipboard.
 */
export function ShareSiteLink({ siteId, title }: { siteId: string; title: string }) {
  const [copied, setCopied] = useState(false)

  const handleShare = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    const shareUrl = `${window.location.origin}/site.html?id=${siteId}`
    const result = await shareOrCopy(`${title} - Ancient Nerds`, shareUrl)
    if (result !== 'copied') return
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      className={`site-card-action-link${copied ? ' copied' : ''}`}
      onClick={handleShare}
      title={copied ? 'Link copied!' : 'Share site'}
    >
      {copied ? (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
      )}
      {copied ? 'Copied' : 'Share'}
    </button>
  )
}
