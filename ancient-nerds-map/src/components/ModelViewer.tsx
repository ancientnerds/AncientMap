import { useEffect, useCallback, useState } from 'react'
import { createPortal } from 'react-dom'

// Model data structure (compatible with both legacy and unified connectors)
interface SketchfabModel {
  uid: string
  name: string
  thumbnail: string
  embedUrl?: string
  creator?: string
  creatorUrl?: string
  viewCount?: number
  likeCount?: number
  viewerUrl?: string
}

interface ModelViewerProps {
  models: SketchfabModel[]
  currentIndex: number
  onClose: () => void
  onNavigate: (index: number) => void
}

export default function ModelViewer({
  models,
  currentIndex,
  onClose,
  onNavigate,
}: ModelViewerProps) {
  const current = models[currentIndex]
  const hasMultiple = models.length > 1
  const [isLoading, setIsLoading] = useState(true)

  const handlePrev = useCallback(() => {
    setIsLoading(true)
    onNavigate(currentIndex > 0 ? currentIndex - 1 : models.length - 1)
  }, [currentIndex, models.length, onNavigate])

  const handleNext = useCallback(() => {
    setIsLoading(true)
    onNavigate(currentIndex < models.length - 1 ? currentIndex + 1 : 0)
  }, [currentIndex, models.length, onNavigate])

  // Reset loading state when model changes
  useEffect(() => {
    setIsLoading(true)
  }, [currentIndex])

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          onClose()
          break
        case 'ArrowLeft':
          if (hasMultiple) handlePrev()
          break
        case 'ArrowRight':
          if (hasMultiple) handleNext()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose, handlePrev, handleNext, hasMultiple])

  // Prevent body scroll when viewer is open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  if (!current) return null

  // Format large numbers (e.g., 1234 -> 1.2K)
  const formatCount = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  return createPortal(
    <div className="model-viewer-overlay" onClick={onClose}>
      <div className="model-viewer-content" onClick={(e) => e.stopPropagation()}>
        {/* Close button */}
        <button className="model-viewer-close" onClick={onClose} title="Close (Esc)">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {/* Navigation buttons */}
        {hasMultiple && (
          <>
            <button className="model-viewer-nav model-viewer-prev" onClick={handlePrev} title="Previous">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <button className="model-viewer-nav model-viewer-next" onClick={handleNext} title="Next">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </>
        )}

        {/* 3D Model iframe */}
        <div className="model-viewer-iframe-container">
          {isLoading && (
            <div className="model-viewer-loading">
              <div className="model-viewer-spinner" />
              <span>Loading 3D model...</span>
            </div>
          )}
          <iframe
            src={current.embedUrl}
            title={current.name}
            allowFullScreen
            allow="autoplay; fullscreen; xr-spatial-tracking"
            onLoad={() => setIsLoading(false)}
            style={{ opacity: isLoading ? 0 : 1 }}
          />
        </div>

        {/* Caption and attribution */}
        <div className="model-viewer-caption">
          <div className="model-viewer-info">
            <div className="model-viewer-title">{current.name}</div>
            <div className="model-viewer-creator">
              by{' '}
              <a href={current.creatorUrl} target="_blank" rel="noopener noreferrer">
                {current.creator}
              </a>
            </div>
          </div>

          {(current.viewCount !== undefined || current.likeCount !== undefined) && (
            <div className="model-viewer-stats">
              {current.viewCount !== undefined && (
                <span className="model-viewer-stat" title="Views">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                  {formatCount(current.viewCount)}
                </span>
              )}
              {current.likeCount !== undefined && (
                <span className="model-viewer-stat" title="Likes">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                  </svg>
                  {formatCount(current.likeCount)}
                </span>
              )}
            </div>
          )}

          <a
            href={current.viewerUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="model-viewer-sketchfab-link"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.568 16.051l-5.568 3.217-5.568-3.217V7.949l5.568-3.217 5.568 3.217v8.102z"/>
            </svg>
            View on Sketchfab
          </a>

          {hasMultiple && (
            <div className="model-viewer-counter">
              {currentIndex + 1} / {models.length}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
