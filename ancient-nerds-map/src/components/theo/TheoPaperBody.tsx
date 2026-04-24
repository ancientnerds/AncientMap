/**
 * Shared segment renderer for Theo research papers.
 *
 * Extracted from the previously-duplicated JSX in `ResearchPaperPage.tsx` and
 * `TheoReportOverlay.tsx` so both read-only renderers (and the upcoming
 * per-section approval editor) agree on DOM shape, lightbox wiring, and
 * figcaption-as-source behaviour. Callers supply their own `mdComponents` so
 * citation-link and anchor styling can stay page-specific.
 */
import { forwardRef } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { PaperSegment } from './galleryParser'
import { TheoCarousel } from './TheoCarousel'

interface TheoPaperBodyProps {
  segments: PaperSegment[]
  mdComponents: Components
  figureStartIndex: Map<string, number>
  onImageClick: (lightboxIndex: number) => void
  /** Container className. Two existing sites use `.theo-paper-body` and `.theo-report-body`. */
  className?: string
}

const TheoPaperBody = forwardRef<HTMLDivElement, TheoPaperBodyProps>(function TheoPaperBody(
  { segments, mdComponents, figureStartIndex, onImageClick, className = 'theo-paper-body theo-md-body' },
  ref,
) {
  return (
    <div className={className} ref={ref}>
      {segments.map((seg, idx) => {
        if (seg.kind === 'figure') {
          const lbIdx = figureStartIndex.get(`f-${idx}`) ?? 0
          return (
            <figure key={`f-${idx}`} className="theo-inline-figure">
              <img
                src={seg.figure.src}
                alt={seg.figure.title}
                loading="lazy"
                onClick={() => onImageClick(lbIdx)}
              />
              {seg.figure.caption && (
                <figcaption>
                  {seg.figure.sourceUrl ? (
                    <a href={seg.figure.sourceUrl} target="_blank" rel="noopener noreferrer">
                      <em>{seg.figure.caption}</em>
                    </a>
                  ) : (
                    <em>{seg.figure.caption}</em>
                  )}
                </figcaption>
              )}
            </figure>
          )
        }
        if (seg.kind === 'carousel') {
          return (
            <TheoCarousel
              key={`c-${idx}`}
              galleryId={seg.galleryId}
              figures={seg.figures}
            />
          )
        }
        if (seg.kind === 'mosaic') {
          const cols = Math.min(3, seg.figures.length)
          const mosaicStart = figureStartIndex.get(`m-${idx}`) ?? 0
          return (
            <div
              key={`m-${idx}`}
              className={`theo-figure-mosaic theo-figure-mosaic--cols-${cols}`}
            >
              {seg.figures.map((fig, fIdx) => (
                <figure key={`m-${idx}-${fIdx}`} className="theo-figure-mosaic-item">
                  <img
                    src={fig.src}
                    alt={fig.title}
                    loading="lazy"
                    onClick={() => onImageClick(mosaicStart + fIdx)}
                  />
                  {fig.caption && (
                    <figcaption>
                      {fig.sourceUrl ? (
                        <a href={fig.sourceUrl} target="_blank" rel="noopener noreferrer">
                          <em>{fig.caption}</em>
                        </a>
                      ) : (
                        <em>{fig.caption}</em>
                      )}
                    </figcaption>
                  )}
                </figure>
              ))}
            </div>
          )
        }
        return (
          <ReactMarkdown
            key={`t-${idx}`}
            remarkPlugins={[remarkGfm]}
            components={mdComponents}
          >
            {seg.content}
          </ReactMarkdown>
        )
      })}
    </div>
  )
})

export default TheoPaperBody
