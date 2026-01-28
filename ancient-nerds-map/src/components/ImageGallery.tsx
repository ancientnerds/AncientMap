import { useState } from 'react'
import ImageLightbox, { LightboxImage } from './ImageLightbox'

export interface GalleryImage {
  thumb: string
  full: string
  title?: string
  photographer?: string
  photographerUrl?: string
  wikimediaUrl?: string
  license?: string
  source?: 'local' | 'wikipedia'
}

interface ImageGalleryProps {
  siteId: string
  siteName: string
  prefetchedImages?: { wiki: GalleryImage[] } | null
}

export default function ImageGallery({
  siteId: _siteId,
  siteName: _siteName,
  prefetchedImages,
}: ImageGalleryProps) {
  void _siteId
  void _siteName
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  // Get images from prefetched data
  const wikipediaImages = prefetchedImages?.wiki || []

  const lightboxImages: LightboxImage[] = wikipediaImages.map((img) => ({
    src: img.full,
    title: img.title,
    photographer: img.photographer,
    photographerUrl: img.photographerUrl,
    wikimediaUrl: img.wikimediaUrl,
    license: img.license,
  }))

  return (
    <div className="gallery-container">
      {wikipediaImages.length === 0 ? (
        <div className="gallery-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
          <span>No photos available</span>
        </div>
      ) : (
        <div className="gallery-grid">
          {wikipediaImages.map((image, index) => (
            <div
              key={`wiki-${index}`}
              className="gallery-item"
              onClick={() => setLightboxIndex(index)}
              title={image.title || 'Click to enlarge'}
            >
              <img src={image.thumb} alt={image.title || `Photo ${index + 1}`} loading="lazy" />
              <div className="gallery-item-badge wikipedia">W</div>
              <div className="gallery-item-overlay">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  <line x1="11" y1="8" x2="11" y2="14" />
                  <line x1="8" y1="11" x2="14" y2="11" />
                </svg>
              </div>
              {image.photographer && (
                <div className="gallery-item-credit">{image.photographer}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {lightboxIndex !== null && (
        <ImageLightbox
          images={lightboxImages}
          currentIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </div>
  )
}
