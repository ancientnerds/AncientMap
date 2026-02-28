import { memo } from 'react'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import LazyImage from './LazyImage'

export interface SiteResultItemProps {
  id: string
  title: string
  category?: string
  categoryColor?: string
  location?: string
  period?: string
  periodColor?: string
  sourceName?: string
  sourceColor?: string
  thumbnailUrl?: string
  selected?: boolean
  showSource?: boolean
  showInfoBtn?: boolean
  onMainClick?: (e: React.MouseEvent) => void
  onInfoClick?: () => void
  onHoverEnter?: () => void
  onHoverLeave?: () => void
}

function SiteResultItem({
  title,
  category,
  categoryColor,
  location,
  period,
  periodColor,
  sourceName,
  sourceColor,
  thumbnailUrl,
  selected,
  showSource = false,
  showInfoBtn = true,
  onMainClick,
  onInfoClick,
  onHoverEnter,
  onHoverLeave,
}: SiteResultItemProps) {
  const flagUrl = location ? getCountryFlatFlagUrl(location) : null

  return (
    <div
      className={`search-result-item${selected ? ' selected' : ''}`}
      onMouseEnter={onHoverEnter}
      onMouseLeave={onHoverLeave}
    >
      <div className="search-result-main" onClick={onMainClick}>
        {thumbnailUrl && (
          <LazyImage src={thumbnailUrl} alt="" className="search-result-thumb" />
        )}
        <div className="search-result-content">
          <div className="search-result-title">{title}</div>
          {location && (
            <div className="search-result-location">
              {location}
              {flagUrl && (
                <img
                  src={flagUrl}
                  alt=""
                  className="search-result-flag"
                />
              )}
            </div>
          )}
          <div className="search-result-meta">
            {category && (
              <span className="search-result-badge" style={{ borderColor: categoryColor, color: categoryColor }}>{category}</span>
            )}
            {period && (
              <span className="search-result-badge" style={{ borderColor: periodColor, color: periodColor }}>{period}</span>
            )}
            {showSource && sourceName && (
              <span className="search-result-badge search-result-source" style={{ borderColor: sourceColor, color: sourceColor }}>{sourceName}</span>
            )}
          </div>
        </div>
      </div>
      {showInfoBtn && (
        <button
          className="search-result-info-btn"
          onClick={onInfoClick}
          title="Open details"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
            <polyline points="15 3 21 3 21 9"></polyline>
            <line x1="10" y1="14" x2="21" y2="3"></line>
          </svg>
        </button>
      )}
    </div>
  )
}

export default memo(SiteResultItem)
