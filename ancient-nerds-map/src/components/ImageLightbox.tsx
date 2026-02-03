import { useEffect, useCallback, useState, useRef } from 'react'
import { createPortal } from 'react-dom'

export interface LightboxImage {
  src: string
  title?: string
  photographer?: string
  photographerUrl?: string
  // Source type can be any connector ID from the backend
  sourceType?: 'wikimedia' | 'david-rumsey' | 'met-museum' | 'smithsonian'
             | 'europeana' | 'loc' | 'british-museum' | 'sketchfab' | string
  sourceUrl?: string
  license?: string
}

interface ImageLightboxProps {
  images: LightboxImage[]
  currentIndex: number
  onClose: () => void
  onNavigate: (index: number) => void
}

export default function ImageLightbox({
  images,
  currentIndex,
  onClose,
  onNavigate,
}: ImageLightboxProps) {
  const current = images[currentIndex]
  const hasMultiple = images.length > 1

  // Zoom and pan state
  const [zoom, setZoom] = useState(1)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 })
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })

  const containerRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const panStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 })

  // Calculate max zoom based on image natural size vs container
  const maxZoom = naturalSize.width > 0 && containerSize.width > 0
    ? Math.max(2, naturalSize.width / containerSize.width)
    : 4

  // Reset zoom/pan when navigating to new image
  useEffect(() => {
    setZoom(1)
    setPosition({ x: 0, y: 0 })
  }, [currentIndex])

  // Get container size on mount and resize
  useEffect(() => {
    const updateContainerSize = () => {
      if (containerRef.current) {
        setContainerSize({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    }
    updateContainerSize()
    window.addEventListener('resize', updateContainerSize)
    return () => window.removeEventListener('resize', updateContainerSize)
  }, [])

  // Handle image load to get natural dimensions
  const handleImageLoad = () => {
    if (imageRef.current) {
      setNaturalSize({
        width: imageRef.current.naturalWidth,
        height: imageRef.current.naturalHeight,
      })
    }
  }

  const handlePrev = useCallback(() => {
    onNavigate(currentIndex > 0 ? currentIndex - 1 : images.length - 1)
  }, [currentIndex, images.length, onNavigate])

  const handleNext = useCallback(() => {
    onNavigate(currentIndex < images.length - 1 ? currentIndex + 1 : 0)
  }, [currentIndex, images.length, onNavigate])

  // Handle scroll wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.15 : 0.15
    setZoom(prev => {
      const newZoom = Math.max(1, Math.min(maxZoom, prev + delta))
      // Reset position when zooming out to 1
      if (newZoom === 1) {
        setPosition({ x: 0, y: 0 })
      }
      return newZoom
    })
  }, [maxZoom])

  // Handle click to toggle zoom
  const handleImageClick = useCallback(() => {
    if (isPanning) return // Don't toggle if we were panning

    if (zoom === 1) {
      // Zoom in to 2x centered on click position
      setZoom(2)
    } else {
      // Zoom out
      setZoom(1)
      setPosition({ x: 0, y: 0 })
    }
  }, [zoom, isPanning])

  // Pan handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (zoom <= 1) return
    e.preventDefault()
    setIsPanning(true)
    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      posX: position.x,
      posY: position.y,
    }
  }, [zoom, position])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning || zoom <= 1) return

    const deltaX = e.clientX - panStartRef.current.x
    const deltaY = e.clientY - panStartRef.current.y

    // Calculate bounds based on zoom level
    const maxPanX = (containerSize.width * (zoom - 1)) / 2
    const maxPanY = (containerSize.height * (zoom - 1)) / 2

    setPosition({
      x: Math.max(-maxPanX, Math.min(maxPanX, panStartRef.current.posX + deltaX)),
      y: Math.max(-maxPanY, Math.min(maxPanY, panStartRef.current.posY + deltaY)),
    })
  }, [isPanning, zoom, containerSize])

  const handleMouseUp = useCallback(() => {
    setIsPanning(false)
  }, [])

  // Touch handlers for mobile
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (zoom <= 1 || e.touches.length !== 1) return
    const touch = e.touches[0]
    setIsPanning(true)
    panStartRef.current = {
      x: touch.clientX,
      y: touch.clientY,
      posX: position.x,
      posY: position.y,
    }
  }, [zoom, position])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isPanning || zoom <= 1 || e.touches.length !== 1) return

    const touch = e.touches[0]
    const deltaX = touch.clientX - panStartRef.current.x
    const deltaY = touch.clientY - panStartRef.current.y

    const maxPanX = (containerSize.width * (zoom - 1)) / 2
    const maxPanY = (containerSize.height * (zoom - 1)) / 2

    setPosition({
      x: Math.max(-maxPanX, Math.min(maxPanX, panStartRef.current.posX + deltaX)),
      y: Math.max(-maxPanY, Math.min(maxPanY, panStartRef.current.posY + deltaY)),
    })
  }, [isPanning, zoom, containerSize])

  const handleTouchEnd = useCallback(() => {
    setIsPanning(false)
  }, [])

  // Zoom controls
  const zoomIn = () => setZoom(prev => Math.min(maxZoom, prev + 0.5))
  const zoomOut = () => {
    setZoom(prev => {
      const newZoom = Math.max(1, prev - 0.5)
      if (newZoom === 1) setPosition({ x: 0, y: 0 })
      return newZoom
    })
  }
  const zoomReset = () => {
    setZoom(1)
    setPosition({ x: 0, y: 0 })
  }

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          if (zoom > 1) {
            zoomReset()
          } else {
            onClose()
          }
          break
        case 'ArrowLeft':
          if (hasMultiple && zoom === 1) handlePrev()
          break
        case 'ArrowRight':
          if (hasMultiple && zoom === 1) handleNext()
          break
        case '+':
        case '=':
          zoomIn()
          break
        case '-':
          zoomOut()
          break
        case '0':
          zoomReset()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose, handlePrev, handleNext, hasMultiple, zoom])

  // Prevent body scroll when lightbox is open
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  // Global mouse up handler
  useEffect(() => {
    const handleGlobalMouseUp = () => setIsPanning(false)
    window.addEventListener('mouseup', handleGlobalMouseUp)
    window.addEventListener('touchend', handleGlobalMouseUp)
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp)
      window.removeEventListener('touchend', handleGlobalMouseUp)
    }
  }, [])

  if (!current) return null

  const cursorStyle = zoom > 1 ? (isPanning ? 'grabbing' : 'grab') : 'zoom-in'

  return createPortal(
    <div className="lightbox-overlay" onClick={onClose}>
      <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
        {/* Close button */}
        <button className="lightbox-close" onClick={onClose} title="Close (Esc)">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {/* Navigation buttons */}
        {hasMultiple && zoom === 1 && (
          <>
            <button className="lightbox-nav lightbox-prev" onClick={handlePrev} title="Previous">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <button className="lightbox-nav lightbox-next" onClick={handleNext} title="Next">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </>
        )}

        {/* Main image with zoom/pan */}
        <div
          ref={containerRef}
          className={`lightbox-image-container ${zoom > 1 ? 'zoomed' : ''} ${isPanning ? 'panning' : ''}`}
          style={{ cursor: cursorStyle }}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onClick={handleImageClick}
        >
          <img
            ref={imageRef}
            src={current.src}
            alt={current.title || 'Site image'}
            className="lightbox-image"
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
            }}
            onLoad={handleImageLoad}
            draggable={false}
          />
        </div>

        {/* Zoom controls */}
        <div className="lightbox-zoom-controls">
          <button className="lightbox-zoom-btn" onClick={zoomOut} title="Zoom out (-)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </svg>
          </button>
          <span className="lightbox-zoom-level">{Math.round(zoom * 100)}%</span>
          <button className="lightbox-zoom-btn" onClick={zoomIn} title="Zoom in (+)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="11" y1="8" x2="11" y2="14" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </svg>
          </button>
          {zoom > 1 && (
            <button className="lightbox-zoom-btn" onClick={zoomReset} title="Reset zoom (0)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
              </svg>
            </button>
          )}
        </div>

        {/* Caption and attribution */}
        <div className="lightbox-caption">
          {current.title && <div className="lightbox-title">{current.title}</div>}
          <div className="lightbox-attribution">
            {current.photographer && (
              <span>
                Photo by{' '}
                {current.photographerUrl ? (
                  <a href={current.photographerUrl} target="_blank" rel="noopener noreferrer">
                    {current.photographer}
                  </a>
                ) : (
                  current.photographer
                )}
              </span>
            )}
            {current.license && <span className="lightbox-license">{current.license}</span>}
            {current.sourceUrl && current.sourceType === 'wikimedia' && (
              <a href={current.sourceUrl} target="_blank" rel="noopener noreferrer" className="lightbox-source-link">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                </svg>
                Wikimedia
              </a>
            )}
            {current.sourceUrl && current.sourceType === 'david-rumsey' && (
              <a href={current.sourceUrl} target="_blank" rel="noopener noreferrer" className="lightbox-source-link">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                  <line x1="3" y1="9" x2="21" y2="9"></line>
                  <line x1="9" y1="21" x2="9" y2="9"></line>
                </svg>
                David Rumsey
              </a>
            )}
            {current.sourceUrl && current.sourceType === 'met-museum' && (
              <a href={current.sourceUrl} target="_blank" rel="noopener noreferrer" className="lightbox-source-link">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 21h18"></path>
                  <path d="M5 21V7l7-4 7 4v14"></path>
                  <path d="M9 21v-6h6v6"></path>
                </svg>
                Met Museum
              </a>
            )}
            {current.sourceUrl && current.sourceType === 'smithsonian' && (
              <a href={current.sourceUrl} target="_blank" rel="noopener noreferrer" className="lightbox-source-link">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 21h18"></path>
                  <path d="M9 21V9h6v12"></path>
                  <path d="M5 21V3h14v18"></path>
                  <path d="M9 6h6"></path>
                </svg>
                Smithsonian
              </a>
            )}
          </div>
          {hasMultiple && (
            <div className="lightbox-counter">
              {currentIndex + 1} / {images.length}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
