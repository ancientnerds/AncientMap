import type { GalleryGridProps } from '../types'
import { SourceFavicon } from './galleryUtils'
import LazyImage from '../../LazyImage'

export function GalleryGrid({ items, onItemClick }: GalleryGridProps) {
  return (
    <div className="gallery-grid-container">
      <div className="gallery-grid">
        {items.map((item, index) => (
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
    </div>
  )
}
