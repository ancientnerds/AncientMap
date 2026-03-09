import { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { UnifiedGalleryItem } from '../types'

const PROXY_BASE = import.meta.env.DEV ? 'http://localhost:8765' : '/webcam-proxy'
const MAX_ZOOM = 8

interface WebcamStreamOverlayProps {
  item: UnifiedGalleryItem
  onClose: () => void
}

function useLocalTime(timezone: string) {
  const [time, setTime] = useState('')
  const [icon, setIcon] = useState('\u2600')

  useEffect(() => {
    const update = () => {
      try {
        const fmt = new Intl.DateTimeFormat('en-GB', {
          timeZone: timezone,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        })
        setTime(fmt.format(new Date()))
        const h = parseInt(new Intl.DateTimeFormat('en-GB', {
          timeZone: timezone, hour: 'numeric', hour12: false,
        }).format(new Date()))
        setIcon(h >= 6 && h < 20 ? '\u2600' : '\uD83C\uDF19')
      } catch { /* invalid tz */ }
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [timezone])

  return { time, icon }
}

export function WebcamStreamOverlay({ item, onClose }: WebcamStreamOverlayProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<{ destroy: () => void } | null>(null)
  const feedRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [muted, setMuted] = useState(true)
  const [showHint, setShowHint] = useState(true)
  const [zoomVisible, setZoomVisible] = useState(false)

  // Pixel-based zoom & pan (matching test page)
  const pz = useRef({ scale: 1, x: 0, y: 0 })
  const dragState = useRef({ active: false, startX: 0, startY: 0, origX: 0, origY: 0 })
  const touchState = useRef({ initDist: 0, initScale: 1 })
  const zoomHideTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const original = item.original as Record<string, unknown>
  const pageUrl = original.pageUrl as string
  const timezone = original.timezone as string
  const region = original.region as string
  const flag = original.flag as string

  const { time: localTime, icon: timeIcon } = useLocalTime(timezone)

  // Apply transform to video element
  const applyTransform = useCallback(() => {
    const feed = feedRef.current
    const video = videoRef.current
    if (!feed || !video) return

    const { scale, x, y } = pz.current
    // Clamp pan
    if (scale <= 1) {
      pz.current.x = 0
      pz.current.y = 0
    } else {
      const rect = feed.getBoundingClientRect()
      const maxX = rect.width * (scale - 1)
      const maxY = rect.height * (scale - 1)
      pz.current.x = Math.max(-maxX, Math.min(0, x))
      pz.current.y = Math.max(-maxY, Math.min(0, y))
    }

    video.style.transform = `translate(${pz.current.x}px, ${pz.current.y}px) scale(${scale})`

    // Show zoom level
    const isZoomed = scale > 1.05
    setZoomVisible(isZoomed)
    if (isZoomed) setShowHint(false)

    // Auto-hide zoom indicator
    if (zoomHideTimer.current) clearTimeout(zoomHideTimer.current)
    if (isZoomed) {
      zoomHideTimer.current = setTimeout(() => setZoomVisible(false), 2000)
    }
  }, [])

  const resetZoom = useCallback(() => {
    pz.current = { scale: 1, x: 0, y: 0 }
    if (videoRef.current) videoRef.current.style.transform = ''
    setZoomVisible(false)
    setShowHint(true)
  }, [])

  // HLS stream init
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
          maxBufferLength: 10,
          liveSyncDurationCount: 3,
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

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Wheel zoom — zoom toward cursor position (matching test page)
  useEffect(() => {
    const feed = feedRef.current
    if (!feed) return

    const handler = (e: WheelEvent) => {
      e.preventDefault()

      const rect = feed.getBoundingClientRect()
      const cursorX = e.clientX - rect.left
      const cursorY = e.clientY - rect.top

      const oldScale = pz.current.scale
      const delta = e.deltaY > 0 ? 0.85 : 1.18
      pz.current.scale = Math.max(1, Math.min(MAX_ZOOM, oldScale * delta))

      if (pz.current.scale > 1) {
        const ratio = pz.current.scale / oldScale
        pz.current.x = cursorX - ratio * (cursorX - pz.current.x)
        pz.current.y = cursorY - ratio * (cursorY - pz.current.y)
      }

      applyTransform()
    }
    feed.addEventListener('wheel', handler, { passive: false })
    return () => feed.removeEventListener('wheel', handler)
  }, [applyTransform])

  // Mouse drag to pan (pixel-based like test page)
  useEffect(() => {
    const feed = feedRef.current
    if (!feed) return

    const onDown = (e: MouseEvent) => {
      if (pz.current.scale <= 1) return
      e.preventDefault()
      dragState.current = {
        active: true,
        startX: e.clientX,
        startY: e.clientY,
        origX: pz.current.x,
        origY: pz.current.y,
      }
      feed.style.cursor = 'grabbing'
    }

    const onMove = (e: MouseEvent) => {
      if (!dragState.current.active) return
      pz.current.x = dragState.current.origX + (e.clientX - dragState.current.startX)
      pz.current.y = dragState.current.origY + (e.clientY - dragState.current.startY)
      applyTransform()
    }

    const onUp = () => {
      if (!dragState.current.active) return
      dragState.current.active = false
      feed.style.cursor = pz.current.scale > 1 ? 'grab' : ''
    }

    feed.addEventListener('mousedown', onDown)
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      feed.removeEventListener('mousedown', onDown)
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [applyTransform])

  // Double-click to reset
  useEffect(() => {
    const feed = feedRef.current
    if (!feed) return
    const handler = () => resetZoom()
    feed.addEventListener('dblclick', handler)
    return () => feed.removeEventListener('dblclick', handler)
  }, [resetZoom])

  // Touch: pinch-to-zoom + drag-to-pan
  useEffect(() => {
    const feed = feedRef.current
    if (!feed) return

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        touchState.current.initDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
        touchState.current.initScale = pz.current.scale
      } else if (e.touches.length === 1 && pz.current.scale > 1) {
        dragState.current = {
          active: true,
          startX: e.touches[0].clientX,
          startY: e.touches[0].clientY,
          origX: pz.current.x,
          origY: pz.current.y,
        }
      }
    }

    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        e.preventDefault()
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
        pz.current.scale = Math.max(1, Math.min(MAX_ZOOM,
          touchState.current.initScale * (dist / touchState.current.initDist)
        ))
        applyTransform()
      } else if (e.touches.length === 1 && pz.current.scale > 1) {
        pz.current.x = dragState.current.origX + (e.touches[0].clientX - dragState.current.startX)
        pz.current.y = dragState.current.origY + (e.touches[0].clientY - dragState.current.startY)
        applyTransform()
      }
    }

    feed.addEventListener('touchstart', onTouchStart, { passive: true })
    feed.addEventListener('touchmove', onTouchMove, { passive: false })
    return () => {
      feed.removeEventListener('touchstart', onTouchStart)
      feed.removeEventListener('touchmove', onTouchMove)
    }
  }, [applyTransform])

  const toggleFullscreen = useCallback(() => {
    const el = bodyRef.current
    if (!el) return
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      el.requestFullscreen?.()
    }
  }, [])

  const flagImg = flag
    ? <img src={`https://flagcdn.com/16x12/${flag}.png`} alt="" style={{ height: 10, borderRadius: 1, marginRight: 4, verticalAlign: 'middle' }} />
    : null

  return createPortal(
    <div className="webcam-stream-overlay" onClick={onClose}>
      <div ref={bodyRef} className="webcam-stream-body" onClick={e => e.stopPropagation()}>
        <button className="webcam-stream-close" onClick={onClose} title="Close (Esc)">&times;</button>
        <div
          ref={feedRef}
          className="webcam-stream-feed"
          style={{ cursor: pz.current.scale > 1 ? 'grab' : 'default' }}
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
              transformOrigin: '0 0',
              willChange: 'transform',
              pointerEvents: 'none',
              userSelect: 'none',
            }}
          />
          <a
            className="webcam-source-watermark"
            href={pageUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
          >
            <img src="/images/skylinewebcams.svg" alt="SkylineWebcams" className="webcam-source-logo" />
          </a>
          <div className={`webcam-zoom-level ${zoomVisible ? 'visible' : ''}`}>
            {pz.current.scale.toFixed(1)}x
          </div>
          {showHint && !error && !loading && (
            <div className="webcam-zoom-hint">
              Scroll to zoom &middot; Drag to pan &middot; Double-click to reset
            </div>
          )}
        </div>
        <div className="webcam-stream-bar">
          <div>
            <div className="webcam-stream-title">{item.title}</div>
            <div className="webcam-stream-sub">
              {flagImg}{region}
              {localTime && <> &middot; {timeIcon} {localTime} local time</>}
            </div>
          </div>
          <div className="webcam-stream-actions">
            <button className="webcam-lb-btn secondary" onClick={() => setMuted(!muted)} title={muted ? 'Unmute' : 'Mute'}>
              {muted ? '\uD83D\uDD07' : '\uD83D\uDD0A'}
            </button>
            <button className="webcam-lb-btn secondary" onClick={toggleFullscreen} title="Fullscreen">
              &#x26F6;
            </button>
            <a
              className="webcam-lb-btn primary"
              href={pageUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Watch on SkylineWebcams &#x2197;
            </a>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}
