import LazyImage from './LazyImage'
import { SiteBadges } from './metadata/SiteBadges'
import { MetadataBadge } from './metadata/MetadataBadge'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { extractCountry } from '../utils/searchUtils'
import { formatCoord } from '../utils/formatters'
import type { SiteData } from '../data/sites'
import './site-card.css'

// Keep a reference to the globe window so we can message it without reloading
let globeWindow: Window | null = null

interface SiteCardProps {
  site: SiteData
  sourceName?: string
  sourceColor?: string
  onClick: () => void
}

export function SiteCard({ site, sourceName, sourceColor, onClick }: SiteCardProps) {
  const country = extractCountry(site.location)
  const flagUrl = country !== 'Unknown' ? getCountryFlatFlagUrl(country) : null
  const [lng, lat] = site.coordinates
  const hasCoords = !isNaN(lat) && !isNaN(lng) && (lat !== 0 || lng !== 0)

  const handleViewOnGlobe = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    // If we have a live globe tab, message it directly — no reload
    if (globeWindow && !globeWindow.closed) {
      globeWindow.postMessage({ type: 'focus-site', siteId: site.id, title: site.title }, '*')
      globeWindow.focus()
      return
    }

    // No globe tab open — open one with ?focus= param
    globeWindow = window.open(`/globe.html?focus=${site.id}`, 'ancient-nerds-globe')
  }

  return (
    <div className="site-card" onClick={onClick} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onClick() }}>
      {site.image && (
        <div className="site-card-hero">
          <div className="site-card-hero-shimmer" />
          <LazyImage src={site.image} alt={site.title} overlay className="site-card-hero-img" />
          <h3 className="site-card-title">{site.title}</h3>
        </div>
      )}

      <div className="site-card-body">
        {!site.image && <h3 className="site-card-title-plain">{site.title}</h3>}

        <div className="site-card-location">
          {country !== 'Unknown' && (
            <span className="site-card-country">
              {flagUrl && <img src={flagUrl} alt="" className="site-card-flag" loading="lazy" />}
              <span>{country}</span>
            </span>
          )}
          {hasCoords && (
            <span className="site-card-coords">
              {formatCoord(lat, true)}, {formatCoord(lng, false)}
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

        {site.description && (
          <p className="site-card-desc">{site.description}</p>
        )}

        <div className="site-card-footer">
          {sourceName && sourceColor && (
            <MetadataBadge label={sourceName} color={sourceColor} size="sm" />
          )}
          <a
            href={`/globe.html?focus=${site.id}`}
            className="site-card-globe-link"
            onClick={handleViewOnGlobe}
          >
            View on Globe
          </a>
        </div>
      </div>
    </div>
  )
}
