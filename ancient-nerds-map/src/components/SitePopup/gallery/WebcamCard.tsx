import { useState, useEffect } from 'react'
import type { UnifiedGalleryItem } from '../types'

interface WebcamCardProps {
  item: UnifiedGalleryItem
  onStreamClick: (item: UnifiedGalleryItem) => void
}

export function WebcamCard({ item, onStreamClick }: WebcamCardProps) {
  const original = item.original as Record<string, unknown>
  const timezone = original.timezone as string
  const distanceKm = original.distanceKm as number
  const flag = original.flag as string
  const region = original.region as string

  const [localTime, setLocalTime] = useState('')
  const [isDayTime, setIsDayTime] = useState(true)
  const [imgError, setImgError] = useState(false)

  // Update local time every 30s
  useEffect(() => {
    const update = () => {
      try {
        const fmt = new Intl.DateTimeFormat('en-GB', {
          timeZone: timezone,
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
        const now = new Date()
        setLocalTime(fmt.format(now))

        const hourFmt = new Intl.DateTimeFormat('en-GB', {
          timeZone: timezone,
          hour: 'numeric',
          hour12: false,
        })
        const hour = parseInt(hourFmt.format(now))
        setIsDayTime(hour >= 6 && hour < 20)
      } catch {
        setLocalTime('')
      }
    }
    update()
    const timer = setInterval(update, 30_000)
    return () => clearInterval(timer)
  }, [timezone])

  const distLabel = distanceKm < 1
    ? `${Math.round(distanceKm * 1000)} m`
    : `${Math.round(distanceKm)} km`

  return (
    <div className="webcam-card" onClick={() => onStreamClick(item)}>
      <div className="webcam-thumb-wrap">
        {!imgError ? (
          <img
            src={item.thumb}
            alt={item.title || ''}
            className="webcam-thumb"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        ) : (
          <div className="webcam-thumb-placeholder">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
              <circle cx="12" cy="13" r="4"></circle>
            </svg>
          </div>
        )}
        <div className="webcam-live-badge">LIVE</div>
        {localTime && (
          <div className="webcam-time-badge">
            <span>{isDayTime ? '\u2600' : '\uD83C\uDF19'}</span> {localTime}
          </div>
        )}
      </div>
      <div className="webcam-card-info">
        <span className="webcam-card-name" title={item.title}>{item.title}</span>
        <span className="webcam-card-meta">
          {flag && <img src={`https://flagcdn.com/16x12/${flag}.png`} alt="" className="webcam-flag" />}
          {region} &middot; {distLabel}
        </span>
      </div>
    </div>
  )
}
