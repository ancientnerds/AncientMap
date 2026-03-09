import { useState } from 'react'
import type { UnifiedGalleryItem } from '../types'
import { WebcamCard } from './WebcamCard'
import { WebcamStreamOverlay } from './WebcamStreamOverlay'

interface WebcamGalleryProps {
  items: UnifiedGalleryItem[]
  isLoading: boolean
  isOffline: boolean
}

export function WebcamGallery({ items, isLoading, isOffline }: WebcamGalleryProps) {
  const [activeStream, setActiveStream] = useState<UnifiedGalleryItem | null>(null)

  if (isOffline) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty gallery-offline-notice">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
            <circle cx="12" cy="13" r="4"></circle>
            <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
          </svg>
          <span>Webcams require internet</span>
        </div>
      </div>
    )
  }

  if (isLoading && items.length === 0) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-loading">
          <div className="map-loading-spinner" />
        </div>
      </div>
    )
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
            <circle cx="12" cy="13" r="4"></circle>
          </svg>
          <span>No nearby webcams</span>
          <span className="gallery-subtext">No cameras found within 50 km</span>
        </div>
      </div>
    )
  }

  return (
    <div className="gallery-grid-container">
      <div className="webcam-grid">
        {items.map(item => (
          <WebcamCard
            key={item.id}
            item={item}
            onStreamClick={setActiveStream}
          />
        ))}
      </div>
      <div className="webcam-gallery-attribution">
        Streams by{' '}
        <a href="https://www.skylinewebcams.com" target="_blank" rel="noopener noreferrer">SkylineWebcams</a>
      </div>
      {activeStream && (
        <WebcamStreamOverlay
          item={activeStream}
          onClose={() => setActiveStream(null)}
        />
      )}
    </div>
  )
}
