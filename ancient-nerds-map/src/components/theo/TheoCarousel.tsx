/**
 * TheoCarousel — keyboard-navigable, accessible carousel for multi-image
 * paragraphs in a Theo research paper. Activated when the backend emits
 * `gallery:<id>|` markers on adjacent images.
 */

import { useCallback, useRef, useState } from 'react'
import type { ImageFigure } from './galleryParser'

interface TheoCarouselProps {
  figures: ImageFigure[]
  galleryId: string
}

export function TheoCarousel({ figures, galleryId }: TheoCarouselProps) {
  const [index, setIndex] = useState(0)
  const regionRef = useRef<HTMLDivElement | null>(null)

  const goTo = useCallback(
    (next: number) => {
      if (figures.length === 0) return
      const n = ((next % figures.length) + figures.length) % figures.length
      setIndex(n)
    },
    [figures.length],
  )

  const next = useCallback(() => goTo(index + 1), [goTo, index])
  const prev = useCallback(() => goTo(index - 1), [goTo, index])

  const onKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        next()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        prev()
      }
    },
    [next, prev],
  )

  if (figures.length === 0) return null
  const current = figures[index]

  return (
    <div
      ref={regionRef}
      role="region"
      aria-roledescription="carousel"
      aria-label={`Image gallery ${galleryId}`}
      className="theo-carousel"
      tabIndex={0}
      onKeyDown={onKey}
    >
      <div
        className="theo-carousel-slide"
        role="group"
        aria-roledescription="slide"
        aria-label={`Slide ${index + 1} of ${figures.length}`}
        aria-live="polite"
      >
        <figure>
          <img src={current.src} alt={current.title} loading="lazy" />
          {current.caption && <figcaption>{current.caption}</figcaption>}
          {current.sourceUrl && (
            <a href={current.sourceUrl} target="_blank" rel="noreferrer noopener">
              Source
            </a>
          )}
        </figure>
      </div>
      <div className="theo-carousel-controls">
        <button
          type="button"
          aria-label="Previous image"
          onClick={prev}
          disabled={figures.length < 2}
        >
          ‹
        </button>
        <span aria-hidden="true">
          {index + 1} / {figures.length}
        </span>
        <button
          type="button"
          aria-label="Next image"
          onClick={next}
          disabled={figures.length < 2}
        >
          ›
        </button>
      </div>
      <div className="theo-carousel-dots" role="tablist" aria-label="Image selector">
        {figures.map((fig, i) => (
          <button
            key={fig.src}
            type="button"
            role="tab"
            aria-selected={i === index}
            aria-label={`Show image ${i + 1}: ${fig.title}`}
            onClick={() => goTo(i)}
            className={i === index ? 'active' : ''}
          />
        ))}
      </div>
    </div>
  )
}
