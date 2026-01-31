import { GalleryGrid } from './GalleryGrid'
import type { GalleryContentProps } from '../types'
import type { SmithsonianText } from '../../../services/smithsonianService'

export function GalleryContent({
  activeTab,
  items,
  isLoading,
  isOffline,
  onItemClick
}: GalleryContentProps) {

  // Texts tab - display as a list (books don't have images)
  if (activeTab === 'texts') {
    if (isOffline) {
      return (
        <div className="gallery-grid-container">
          <div className="gallery-empty gallery-offline-notice">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
            </svg>
            <span>Texts require internet</span>
            <span className="gallery-subtext">Smithsonian Libraries is online-only</span>
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
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            <span>No texts found</span>
          </div>
        </div>
      )
    }

    // Display texts as a list with optional book covers
    return (
      <div className="gallery-grid-container">
        <div className="gallery-text-list">
          {items.map((item) => {
            const text = item.original as SmithsonianText
            return (
              <a
                key={item.id}
                href={text.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="gallery-text-item"
              >
                {text.coverUrl ? (
                  <div className="gallery-text-cover">
                    <img src={text.coverUrl} alt="" loading="lazy" />
                  </div>
                ) : (
                  <div className="gallery-text-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                      <line x1="16" y1="13" x2="8" y2="13"></line>
                      <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                  </div>
                )}
                <div className="gallery-text-content">
                  <div className="gallery-text-title">{text.title}</div>
                  {text.author && <div className="gallery-text-author">{text.author}</div>}
                  {text.date && <div className="gallery-text-date">{text.date}</div>}
                  <div className="gallery-text-source">{text.museum}</div>
                </div>
                <svg className="gallery-text-link" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                  <polyline points="15 3 21 3 21 9"></polyline>
                  <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
              </a>
            )
          })}
        </div>
      </div>
    )
  }

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
          <span className="gallery-subtext">Map sources are online-only</span>
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

  // Artifacts tab - show offline notice when offline
  if (activeTab === 'artifacts' && isOffline) {
    return (
      <div className="gallery-grid-container">
        <div className="gallery-empty gallery-offline-notice">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
            <path d="M2 17l10 5 10-5"></path>
            <path d="M2 12l10 5 10-5"></path>
            <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
          </svg>
          <span>Artifacts require internet</span>
          <span className="gallery-subtext">Smithsonian API is online-only</span>
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
