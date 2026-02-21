import type { LocationSectionProps } from '../types'
import { formatCoord } from '../../../utils/formatters'
import { CountryFlag } from '../../metadata'

export function LocationSection({
  location,
  lat,
  lng,
  coordsCopied,
  onCoordsCopy,
  onSetProximity,
  onMinimize
}: LocationSectionProps) {
  return (
    <div className="popup-location-row">
      {location && (
        <>
          <CountryFlag country={location} size="lg" />
          <span className="popup-location-name">{location}</span>
        </>
      )}

      <span className="popup-coords-inline">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="2" y1="12" x2="22" y2="12"></line>
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
        </svg>
        <span className="coords-text">{formatCoord(lat, true)}, {formatCoord(lng, false)}</span>
        <div className="coords-actions">
          <button
            className={`coords-action-btn ${coordsCopied ? 'copied' : ''}`}
            onClick={() => {
              navigator.clipboard.writeText(`${formatCoord(lat, true)}, ${formatCoord(lng, false)}`)
              onCoordsCopy()
            }}
            title="Copy coordinates"
          >
            {coordsCopied ? (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            )}
          </button>
          {onSetProximity && (
            <button
              className="coords-action-btn"
              onClick={() => {
                onSetProximity([lng, lat])
                onMinimize?.()
              }}
              title="Search nearby sites"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            </button>
          )}
        </div>
      </span>
    </div>
  )
}
