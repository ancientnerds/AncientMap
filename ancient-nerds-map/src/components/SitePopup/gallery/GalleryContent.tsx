import { GalleryGrid } from './GalleryGrid'
import type { GalleryContentProps } from '../types'

export function GalleryContent({
  activeTab,
  items,
  isLoading,
  isOffline,
  onItemClick
}: GalleryContentProps) {

  // Maps tab - show offline notice when offline
  if (activeTab === 'maps' && isOffline) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty gallery-offline-notice">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z"/>
            <circle cx="12" cy="10" r="3"/>
            <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
          </svg>
          <span>Historical maps require internet</span>
          <span className="gallery-subtext">David Rumsey Map Collection is online-only</span>
        </div>
      </div>
    )
  }

  // 3D Models tab - show offline notice when offline
  if (activeTab === '3dmodels' && isOffline) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty gallery-offline-notice">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
            <line x1="12" y1="22.08" x2="12" y2="12"/>
            <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
          </svg>
          <span>3D models require internet</span>
          <span className="gallery-subtext">Sketchfab viewer is online-only</span>
        </div>
      </div>
    )
  }

  // Artifacts tab is placeholder only - show Coming Soon
  if (activeTab === 'artifacts') {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
            <path d="M2 17l10 5 10-5"></path>
            <path d="M2 12l10 5 10-5"></path>
          </svg>
          <span>Coming Soon</span>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-loading">
          <div className="map-loading-spinner" />
        </div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
          <span>No {activeTab} found</span>
        </div>
      </div>
    )
  }

  return <GalleryGrid items={items} onItemClick={onItemClick} />
}
