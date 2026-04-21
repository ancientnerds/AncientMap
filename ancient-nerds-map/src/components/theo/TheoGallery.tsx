/**
 * TheoGallery — Slideshow for a group of probative images attached to one
 * paragraph. All images render at the same fixed size (paragraph width),
 * navigated via left/right arrows and dot indicators. Each slide carries a
 * verified/unverified chip so the reviewer can approve images before publish.
 */

import { useState, useCallback, useEffect } from 'react'

export interface TheoGalleryImage {
  src: string
  title: string
  caption: string
  sourceUrl: string
  verified: boolean
}

interface TheoGalleryProps {
  images: TheoGalleryImage[]
}

export default function TheoGallery({ images }: TheoGalleryProps) {
  const [index, setIndex] = useState(0)

  const goPrev = useCallback(() => {
    setIndex(i => (i - 1 + images.length) % images.length)
  }, [images.length])

  const goNext = useCallback(() => {
    setIndex(i => (i + 1) % images.length)
  }, [images.length])

  useEffect(() => {
    if (index >= images.length) setIndex(0)
  }, [images.length, index])

  if (images.length === 0) return null
  const current = images[index]
  const multi = images.length > 1

  return (
    <figure className="theo-gallery">
      <div className="theo-gallery-viewport">
        {multi && (
          <button
            className="theo-gallery-arrow theo-gallery-arrow-left"
            onClick={goPrev}
            aria-label="Previous image"
            type="button"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        )}
        <img
          src={current.src}
          alt={current.title}
          loading="lazy"
          className="theo-gallery-image"
        />
        {multi && (
          <button
            className="theo-gallery-arrow theo-gallery-arrow-right"
            onClick={goNext}
            aria-label="Next image"
            type="button"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        )}
        <span
          className={`theo-gallery-chip theo-gallery-chip-${current.verified ? 'verified' : 'unverified'}`}
          title={current.verified ? 'Visual match verified by VLM' : 'Thematic match — reviewer approval recommended'}
        >
          {current.verified ? '✓ verified' : '? unverified'}
        </span>
        {multi && (
          <span className="theo-gallery-counter">
            {index + 1} / {images.length}
          </span>
        )}
      </div>
      {multi && (
        <div className="theo-gallery-dots" role="tablist">
          {images.map((_, i) => (
            <button
              key={i}
              className={`theo-gallery-dot${i === index ? ' is-active' : ''}`}
              onClick={() => setIndex(i)}
              aria-label={`Go to image ${i + 1}`}
              aria-selected={i === index}
              role="tab"
              type="button"
            />
          ))}
        </div>
      )}
      <figcaption className="theo-gallery-caption">
        <em>{current.caption}</em>
        {current.sourceUrl && (
          <>
            {' '}
            <a href={current.sourceUrl} target="_blank" rel="noopener noreferrer">
              Source
            </a>
          </>
        )}
      </figcaption>
    </figure>
  )
}
