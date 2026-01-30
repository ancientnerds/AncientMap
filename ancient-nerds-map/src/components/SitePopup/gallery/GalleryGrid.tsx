import type { GalleryGridProps } from '../types'

export function GalleryGrid({ items, onItemClick }: GalleryGridProps) {
  return (
    <div className="gallery-grid-container">
      <div className="gallery-grid">
        {items.map((item, index) => (
          <div
            key={item.id}
            className="gallery-item"
            onClick={() => onItemClick(index)}
            title={item.title || 'Click to enlarge'}
          >
            <img
              src={item.thumb}
              alt={item.title || ''}
              loading="lazy"
              onError={(e) => {
                e.currentTarget.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23333" width="100" height="100"/></svg>'
              }}
            />
            {item.source === 'wikipedia' && (
              <div className="gallery-item-badge wikipedia">W</div>
            )}
            {item.source === 'sketchfab' && (
              <div className="gallery-item-badge sketchfab" title="3D Model">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                </svg>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
