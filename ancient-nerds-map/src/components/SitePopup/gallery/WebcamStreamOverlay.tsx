import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import type { UnifiedGalleryItem } from '../types'

const PROXY_BASE = import.meta.env.DEV ? 'http://localhost:8765' : '/webcam-proxy'

interface WebcamStreamOverlayProps {
  item: UnifiedGalleryItem
  onClose: () => void
}

export function WebcamStreamOverlay({ item, onClose }: WebcamStreamOverlayProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<{ destroy: () => void } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [muted, setMuted] = useState(true)

  const original = item.original as Record<string, unknown>
  const pageUrl = original.pageUrl as string

  useEffect(() => {
    let cancelled = false

    async function initStream() {
      try {
        // Extract stream URL via proxy
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
          // Try native HLS (Safari)
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

  return createPortal(
    <div className="webcam-stream-overlay" onClick={onClose}>
      <div className="webcam-stream-content" onClick={e => e.stopPropagation()}>
        <div className="webcam-stream-header">
          <span className="webcam-stream-title">{item.title}</span>
          <div className="webcam-stream-controls">
            <button onClick={() => setMuted(!muted)} title={muted ? 'Unmute' : 'Mute'}>
              {muted ? '\uD83D\uDD07' : '\uD83D\uDD0A'}
            </button>
            <button onClick={onClose} title="Close">&times;</button>
          </div>
        </div>
        <div className="webcam-stream-video-wrap">
          {loading && <div className="webcam-stream-loading"><div className="map-loading-spinner" /></div>}
          {error && <div className="webcam-stream-error">{error}</div>}
          <video
            ref={videoRef}
            muted={muted}
            playsInline
            autoPlay
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: error ? 'none' : 'block' }}
          />
        </div>
      </div>
    </div>,
    document.body
  )
}
