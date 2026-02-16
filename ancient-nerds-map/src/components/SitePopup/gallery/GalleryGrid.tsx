import { useState, useEffect } from 'react'
import type { GalleryGridProps } from '../types'
import { SourceFavicon } from './galleryUtils'
import LazyImage from '../../LazyImage'

const PAGE_SIZE = 50

export function GalleryGrid({ items, onItemClick }: GalleryGridProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  // Reset when items change (new site selected)
  useEffect(() => { setVisibleCount(PAGE_SIZE) }, [items])

  const visibleItems = items.slice(0, visibleCount)
  const hasMore = visibleCount < items.length

  return (
    <div className="gallery-grid-container">
      <div className="gallery-grid">
        {visibleItems.map((item, index) => (
          <div
            key={`${item.id}-${index}`}
            className="gallery-item"
            onClick={() => onItemClick(index)}
            title={item.title || 'Click to enlarge'}
          >
            <LazyImage
              src={item.thumb}
              alt={item.title || ''}
              fallbackSrc='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23333" width="100" height="100"/></svg>'
            />
            <SourceFavicon
              source={item.source}
              original={item.original as Record<string, unknown>}
              className="gallery-item-favicon"
            />
          </div>
        ))}
      </div>
      {hasMore && (
        <button
          className="gallery-show-more"
          onClick={() => setVisibleCount(prev => prev + PAGE_SIZE)}
        >
          Show more ({items.length - visibleCount} remaining)
        </button>
      )}
    </div>
  )
}
