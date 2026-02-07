/**
 * TooltipOverlay - Hover and selected site tooltips
 * Displays site information on hover and for selected/list-highlighted sites
 */

import { SiteData } from '../../../data/sites'
import { MetadataBadge, CountryFlag } from '../../metadata'
import { getCategoryColor, getPeriodColor } from '../../../constants/colors'

interface TooltipOverlayProps {
  // Main hover tooltip
  showTooltips: boolean
  isFrozen: boolean
  frozenSite: SiteData | null
  hoveredSite: SiteData | null
  tooltipPos: { x: number; y: number }
  tooltipSiteOnFront: boolean
  showMapbox: boolean
  listFrozenSiteIds: string[]
  onTooltipMouseEnter: () => void
  onTooltipMouseLeave: () => void
  onTooltipClick?: (site: SiteData) => void
  onSiteClick?: (site: SiteData | null) => void

  // List-highlighted tooltips (from search/proximity results)
  listHighlightedSites: SiteData[]
  listHighlightedPositions: Map<string, { x: number; y: number }>

  // Horizontal offset to apply to tooltip positions (e.g. when globe is shifted for news feed)
  globeOffsetX?: number
}

export function TooltipOverlay({
  showTooltips,
  isFrozen,
  frozenSite,
  hoveredSite,
  tooltipPos,
  tooltipSiteOnFront,
  showMapbox,
  listFrozenSiteIds,
  onTooltipMouseEnter,
  onTooltipMouseLeave,
  onTooltipClick,
  onSiteClick,
  listHighlightedSites,
  listHighlightedPositions,
  globeOffsetX = 0,
}: TooltipOverlayProps) {
  // Determine which site to display (frozen or hovered)
  const displaySite = isFrozen ? frozenSite : hoveredSite

  return (
    <>
      {/* Main hover/frozen tooltip */}
      {(() => {
        if (!showTooltips) return null
        if (!displaySite) return null
        // Don't show hover tooltip if site is already selected AND the selected label is ready
        // (prevents flicker when transitioning from hover tooltip to selected label)
        if (listFrozenSiteIds.includes(displaySite.id) && listHighlightedPositions.has(displaySite.id)) return null
        // Don't show tooltip if frozen site is on back of globe (wait for fly-to to bring it to front)
        // Skip this check for Mapbox mode (no back-of-globe concept)
        if (isFrozen && !tooltipSiteOnFront && !showMapbox) return null

        return (
          <div
            className="site-hover-tooltip"
            style={{
              left: Math.min(tooltipPos.x + globeOffsetX + 15, window.innerWidth - 200),
              top: tooltipPos.y + 10,
              cursor: 'pointer'
            }}
            onMouseEnter={() => {
              onTooltipMouseEnter()
            }}
            onMouseLeave={() => {
              onTooltipMouseLeave()
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              e.preventDefault()
              e.nativeEvent.stopImmediatePropagation()
              if (onTooltipClick) {
                onTooltipClick(displaySite)
              } else if (onSiteClick) {
                onSiteClick(displaySite)
              }
            }}
          >
            <div className="tooltip-header">
              <div className="tooltip-title">{displaySite.title}</div>
              <CountryFlag country={displaySite.location} size="sm" />
            </div>
            {displaySite.location && (
              <div className="tooltip-location">{displaySite.location}</div>
            )}
            <div className="meta-badges" style={{ marginTop: 6 }}>
              <MetadataBadge label={displaySite.category} color={getCategoryColor(displaySite.category)} size="sm" />
              <MetadataBadge label={displaySite.period} color={getPeriodColor(displaySite.period)} size="sm" />
            </div>
          </div>
        )
      })()}

      {/* Tooltips for selected sites (from globe clicks, search list, or minimized bars) */}
      {/* These are LOCKED until deselected - no hover logic interaction */}
      {showTooltips && listHighlightedSites.map(site => {
        const pos = listHighlightedPositions.get(site.id)
        if (!pos) return null
        return (
          <div
            key={site.id}
            className="site-hover-tooltip selected-site-label"
            style={{
              left: Math.min(pos.x + globeOffsetX + 15, window.innerWidth - 200),
              top: pos.y + 10,
              pointerEvents: 'auto',
              cursor: 'pointer'
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              e.preventDefault()
              e.nativeEvent.stopImmediatePropagation()
              if (onTooltipClick) {
                onTooltipClick(site)
              } else if (onSiteClick) {
                onSiteClick(site)
              }
            }}
          >
            <div className="tooltip-header">
              <div className="tooltip-title">{site.title}</div>
              <CountryFlag country={site.location} size="sm" />
            </div>
            {site.location && (
              <div className="tooltip-location">{site.location}</div>
            )}
            <div className="meta-badges" style={{ marginTop: 6 }}>
              <MetadataBadge label={site.category} color={getCategoryColor(site.category)} size="sm" />
              <MetadataBadge label={site.period} color={getPeriodColor(site.period)} size="sm" />
            </div>
          </div>
        )
      })}
    </>
  )
}
