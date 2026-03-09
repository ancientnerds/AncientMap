import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { UnifiedGalleryItem } from '../types'

const PROXY_BASE = import.meta.env.DEV ? 'http://localhost:8765' : '/webcam-proxy'

const MIN_ZOOM = 1
const MAX_ZOOM = 5
const ZOOM_STEP = 0.3

interface WebcamStreamOverlayProps {
  item: UnifiedGalleryItem
  onClose: () => void
}

export function WebcamStreamOverlay({ item, onClose }: WebcamStreamOverlayProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<{ destroy: () => void } | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [muted, setMuted] = useState(true)

  // Zoom & pan state
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const panStart = useRef({ x: 0, y: 0 })

  const original = item.original as Record<string, unknown>
  const pageUrl = original.pageUrl as string

  useEffect(() => {
    let cancelled = false

    async function initStream() {
      try {
        const resp = await fetch(`${PROXY_BASE}/api/extract?url=${encodeURIComponent(pageUrl)}`)
        const data = await resp.json()

        if (cancelled) return

        if (data.offline) {
          setError('Camera is currently offline')
          setLoading(false)
          return
        }

        if (!data.stream_url) {
          setError('Could not extract stream')
          setLoading(false)
          return
        }

        const streamUrl = `${PROXY_BASE}${data.stream_url}`
        const Hls = (await import('hls.js')).default

        if (cancelled) return

        if (!Hls.isSupported()) {
          if (videoRef.current?.canPlayType('application/vnd.apple.mpegurl')) {
            videoRef.current.src = streamUrl
            videoRef.current.play().catch(() => {})
            setLoading(false)
            return
          }
          setError('HLS not supported in this browser')
          setLoading(false)
          return
        }

        const hls = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
          maxBufferLength: 10,
          maxMaxBufferLength: 30,
        })
        hlsRef.current = hls

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          if (!cancelled && videoRef.current) {
            videoRef.current.play().catch(() => {})
            setLoading(false)
          }
        })

        hls.on(Hls.Events.ERROR, (_: string, data: { fatal: boolean }) => {
          if (data.fatal && !cancelled) {
            setError('Stream playback failed')
            setLoading(false)
          }
        })

        hls.loadSource(streamUrl)
        hls.attachMedia(videoRef.current!)
      } catch {
        if (!cancelled) {
          setError('Failed to connect to stream proxy')
          setLoading(false)
        }
      }
    }

    initStream()

    return () => {
      cancelled = true
      if (hlsRef.current) {
        hlsRef.current.destroy()
        hlsRef.current = null
      }
    }
  }, [pageUrl])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Clamp pan so the video doesn't disappear off-screen
  const clampPan = useCallback((x: number, y: number, z: number) => {
    if (z <= 1) return { x: 0, y: 0 }
    const maxPan = ((z - 1) / z) * 50 // percentage-based limit
    return {
      x: Math.max(-maxPan, Math.min(maxPan, x)),
      y: Math.max(-maxPan, Math.min(maxPan, y)),
    }
  }, [])

  // Scroll to zoom
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const handler = (e: WheelEvent) => {
      e.preventDefault()
      setZoom(prev => {
        const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, prev - e.deltaY * 0.002))
        // Re-clamp pan for the new zoom
        setPan(p => clampPan(p.x, p.y, next))
        return next
      })
    }
    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [clampPan])

  // Mouse drag to pan
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (zoom <= 1) return
    dragging.current = true
    dragStart.current = { x: e.clientX, y: e.clientY }
    panStart.current = { ...pan }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [zoom, pan])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current || !wrapRef.current) return
    const rect = wrapRef.current.getBoundingClientRect()
    const dx = ((e.clientX - dragStart.current.x) / rect.width) * 100
    const dy = ((e.clientY - dragStart.current.y) / rect.height) * 100
    setPan(clampPan(panStart.current.x + dx, panStart.current.y + dy, zoom))
  }, [zoom, clampPan])

  const onPointerUp = useCallback(() => {
    dragging.current = false
  }, [])

  const resetView = useCallback(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }, [])

  const zoomIn = useCallback(() => {
    setZoom(prev => {
      const next = Math.min(MAX_ZOOM, prev + ZOOM_STEP)
      setPan(p => clampPan(p.x, p.y, next))
      return next
    })
  }, [clampPan])

  const zoomOut = useCallback(() => {
    setZoom(prev => {
      const next = Math.max(MIN_ZOOM, prev - ZOOM_STEP)
      setPan(p => clampPan(p.x, p.y, next))
      return next
    })
  }, [clampPan])

  const isZoomed = zoom > 1.01

  return createPortal(
    <div className="webcam-stream-overlay" onClick={onClose}>
      <div className="webcam-stream-content" onClick={e => e.stopPropagation()}>
        <div className="webcam-stream-header">
          <span className="webcam-stream-title">{item.title}</span>
          <div className="webcam-stream-controls">
            <button onClick={zoomIn} title="Zoom in" disabled={zoom >= MAX_ZOOM}>+</button>
            <button onClick={zoomOut} title="Zoom out" disabled={zoom <= MIN_ZOOM}>&minus;</button>
            {isZoomed && <button onClick={resetView} title="Reset zoom">1:1</button>}
            <button onClick={() => setMuted(!muted)} title={muted ? 'Unmute' : 'Mute'}>
              {muted ? '\uD83D\uDD07' : '\uD83D\uDD0A'}
            </button>
            <button onClick={onClose} title="Close">&times;</button>
          </div>
        </div>
        <div
          ref={wrapRef}
          className="webcam-stream-video-wrap"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          style={{ cursor: isZoomed ? 'grab' : 'default', overflow: 'hidden' }}
        >
          {loading && <div className="webcam-stream-loading"><div className="map-loading-spinner" /></div>}
          {error && <div className="webcam-stream-error">{error}</div>}
          <video
            ref={videoRef}
            muted={muted}
            playsInline
            autoPlay
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              display: error ? 'none' : 'block',
              transform: `scale(${zoom}) translate(${pan.x}%, ${pan.y}%)`,
              transformOrigin: 'center center',
              transition: dragging.current ? 'none' : 'transform 0.15s ease-out',
            }}
          />
        </div>
        <div className="webcam-stream-footer">
          <span className="webcam-stream-attribution">
            Stream provided by{' '}
            <a href={pageUrl} target="_blank" rel="noopener noreferrer">SkylineWebcams</a>
            {' \u00B7 '}
            <a href="https://www.skylinewebcams.com" target="_blank" rel="noopener noreferrer">skylinewebcams.com</a>
          </span>
          {isZoomed && (
            <span className="webcam-stream-zoom-level">{Math.round(zoom * 100)}%</span>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
